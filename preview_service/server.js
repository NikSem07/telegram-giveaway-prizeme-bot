const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 8086;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../webapp')));

// PostgreSQL подключение
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
});

// Конфигурация из .env
const BOT_TOKEN = process.env.BOT_TOKEN?.trim();
const BOT_INTERNAL_URL = process.env.BOT_INTERNAL_URL || 'http://127.0.0.1:8088';
const WEBAPP_BASE_URL = process.env.WEBAPP_BASE_URL?.trim();
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

console.log('🎯 PrizeMe Node.js backend starting...');
console.log('📊 PostgreSQL configured');

// Вспомогательные функции
function _normalizeChatId(raw, username = null) {
  try {
    if (raw === null || raw === undefined) {
      return { chatId: null, debug: 'no_raw_chat_id' };
    }

    const s = String(raw).trim();
    
    // Уже корректный формат (-100…)
    if (s.startsWith('-')) {
      return { chatId: parseInt(s), debug: 'chat_id_ok' };
    }

    // Положительное число без префикса
    if (s.match(/^\d+$/)) {
      const fixed = `-100${s}`;
      return { chatId: parseInt(fixed), debug: `patched_from_positive raw=${s} -> ${fixed}` };
    }

    return { chatId: null, debug: `bad_chat_id_format raw=${raw}` };
  } catch (error) {
    return { chatId: null, debug: `normalize_error ${error.name}: ${error.message}` };
  }
}

async function _isMemberLocal(chatId, userId) {
  try {
    const result = await pool.query(
      'SELECT 1 FROM channel_memberships WHERE chat_id = $1 AND user_id = $2',
      [parseInt(chatId), parseInt(userId)]
    );
    return result.rows.length > 0;
  } catch (error) {
    console.log(`[WARNING] Local membership check failed: ${error}`);
    return false;
  }
}

// Валидация Telegram WebApp initData (упрощенная версия)
function _tgCheckMiniAppInitData(initData) {
  try {
    if (!initData) return null;

    console.log(`[CHECK][mini] raw_init_data: ${initData}`);
    
    // Упрощенная версия - только парсинг user
    const params = new URLSearchParams(initData);
    const userEncoded = params.get('user');
    
    if (!userEncoded) return null;
    
    const userJson = decodeURIComponent(userEncoded);
    const user = JSON.parse(userJson);
    
    if (!user || !user.id) return null;
    
    console.log(`[CHECK][mini] USER EXTRACTED: id=${user.id}`);
    
    return {
      user_parsed: user,
      start_param: params.get('start_param') ? decodeURIComponent(params.get('start_param')) : null
    };
  } catch (error) {
    console.log(`[CHECK][mini] ERROR: ${error}`);
    return null;
  }
}

// Проверка членства в канале через Telegram API
async function tgGetChatMember(chatId, userId) {
  try {
    console.log(`[DEBUG] Checking membership: chat_id=${chatId}, user_id=${userId}`);
    
    const response = await fetch(
      `${TELEGRAM_API}/getChatMember?chat_id=${chatId}&user_id=${userId}`,
      { timeout: 10000 }
    );
    
    const data = await response.json();
    console.log(`[DEBUG] getChatMember response:`, data);
    
    if (!data.ok) {
      const errorCode = data.error_code;
      const description = data.description || '';
      
      console.log(`[ERROR] Telegram API error: ${errorCode} - ${description}`);
      
      // Анализ ошибок
      if (description.toLowerCase().includes('bot was kicked')) {
        return { ok: false, debug: 'bot_kicked_from_chat', status: 'kicked' };
      } else if (description.toLowerCase().includes('bot is not a member')) {
        return { ok: false, debug: 'bot_not_member_of_chat', status: 'left' };
      } else if (description.toLowerCase().includes('chat not found')) {
        return { ok: false, debug: 'chat_not_found', status: 'left' };
      } else if (description.toLowerCase().includes('user not found')) {
        return { ok: false, debug: 'user_not_found_in_chat', status: 'left' };
      } else if (description.toLowerCase().includes('not enough rights')) {
        return { ok: false, debug: 'bot_not_admin', status: 'restricted' };
      } else if (errorCode === 400) {
        return { ok: false, debug: `bad_request: ${description}`, status: 'error' };
      } else if (errorCode === 403) {
        return { ok: false, debug: `forbidden: ${description}`, status: 'restricted' };
      } else {
        return { ok: false, debug: `tg_api_error: ${errorCode} ${description}`, status: 'error' };
      }
    }

    const result = data.result;
    const status = (result.status || '').toLowerCase();
    
    console.log(`[DEBUG] User status: ${status}`);
    
    let debugInfo = `status=${status}`;
    let isOk = false;
    
    // Обработка разных статусов
    if (status === 'restricted') {
      const isMember = result.is_member || false;
      debugInfo += `, is_member=${isMember}`;
      isOk = isMember;
    } else {
      isOk = ['creator', 'administrator', 'member'].includes(status);
    }
    
    console.log(`[DEBUG] Final result: ${debugInfo}, is_ok=${isOk}`);
    return { ok: isOk, debug: debugInfo, status };
    
  } catch (error) {
    console.log(`[ERROR] Network error: ${error}`);
    return { ok: false, debug: `network_error: ${error.name}: ${error.message}`, status: 'error' };
  }
}

// Получение информации о чате
async function tgGetChat(ref) {
  try {
    let chatRef;
    if (typeof ref === 'number') {
      chatRef = ref;
    } else {
      let s = String(ref).trim();
      s = s.replace('https://t.me/', '').replace('t.me/', '');
      if (s.startsWith('@')) s = s.substring(1);
      chatRef = s.match(/^-?\d+$/) ? parseInt(s) : `@${s}`;
    }

    const response = await fetch(
      `${TELEGRAM_API}/getChat?chat_id=${chatRef}`,
      { timeout: 10000 }
    );
    
    const data = await response.json();
    if (!data.ok) {
      const desc = data.description || '';
      const code = data.error_code;
      throw new Error(`getChat failed: ${code} ${desc}`);
    }

    return data.result;
  } catch (error) {
    throw error;
  }
}

// Basic health check
app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'PrizeMe Node.js backend is running', timestamp: new Date().toISOString() });
});

// Start server
app.listen(PORT, () => {
  console.log(`🎯 PrizeMe Node.js backend running on port ${PORT}`);
  console.log(`📊 Using existing .env configuration`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
});
