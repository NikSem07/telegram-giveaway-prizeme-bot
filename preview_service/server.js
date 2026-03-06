const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const mime = require('mime-types');

// ЯВНОЕ ПОДКЛЮЧЕНИЕ .env ФАЙЛА
require('dotenv').config({ path: '/root/telegram-giveaway-prizeme-bot/.env' });

const app = express();
const PORT = process.env.PORT || 8086;

// ДИАГНОСТИКА ЗАГРУЗКИ .env
console.log('🔧 .env DIAGNOSTICS:');
console.log('   S3_ENDPOINT:', process.env.S3_ENDPOINT);
console.log('   S3_BUCKET:', process.env.S3_BUCKET);
console.log('   S3_ACCESS_KEY:', process.env.S3_ACCESS_KEY ? '***SET***' : 'NOT SET');
console.log('   S3_SECRET_KEY:', process.env.S3_SECRET_KEY ? '***SET***' : 'NOT SET');
console.log('   BOT_TOKEN:', process.env.BOT_TOKEN ? '***SET***' : 'NOT SET');

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../webapp')));
app.use('/miniapp', express.static(path.join(__dirname, '../webapp'), { index: false }));


// Конфигурация из .env
const BOT_TOKEN = process.env.BOT_TOKEN?.trim();
const WEBAPP_BASE_URL = process.env.WEBAPP_BASE_URL?.trim();
const TELEGRAM_API = BOT_TOKEN ? `https://api.telegram.org/bot${BOT_TOKEN}` : null;
const BOT_INTERNAL_URL = process.env.BOT_INTERNAL_URL || 'http://127.0.0.1:8088';

// Robokassa
const ROBOKASSA_LOGIN     = process.env.ROBOKASSA_LOGIN     || '';
const ROBOKASSA_PASSWORD1 = process.env.ROBOKASSA_PASSWORD1 || '';
const ROBOKASSA_PASSWORD2 = process.env.ROBOKASSA_PASSWORD2 || '';
const ROBOKASSA_IS_TEST        = process.env.ROBOKASSA_IS_TEST === '1' ? 1 : 0;
const ROBOKASSA_TEST_PASSWORD1 = process.env.ROBOKASSA_TEST_PASSWORD1 || '';
const ROBOKASSA_TEST_PASSWORD2 = process.env.ROBOKASSA_TEST_PASSWORD2 || '';
const ROBOKASSA_PROMOTION_PRICE = 9990;


// Логируем конфигурацию при запуске
console.log('🔧 Configuration loaded:');
console.log('   BOT_TOKEN:', BOT_TOKEN ? '***SET***' : 'NOT SET');
console.log('   BOT_INTERNAL_URL:', BOT_INTERNAL_URL);
console.log('   WEBAPP_BASE_URL:', WEBAPP_BASE_URL || 'NOT SET');
console.log('   TELEGRAM_API:', TELEGRAM_API || 'NOT SET (no BOT_TOKEN)');

// PostgreSQL подключение
const pool = new Pool({
  user: 'prizeme_user',
  password: 'Akinneket19!',
  host: 'localhost',
  port: 5432,
  database: 'prizeme_prod',
  ssl: false
});

async function upsertMiniAppUser(user) {
  try {
    if (!user || !user.id) return;

    const userId = Number(user.id);
    if (!Number.isFinite(userId)) return;

    // Telegram username может быть undefined/null/""
    const usernameRaw = (user.username || "").trim();
    const username = usernameRaw.length ? usernameRaw : null;

    // Важно: не затираем username на NULL, если он уже был
    const firstName = (user.first_name || "").trim() || null;
    const langCode = (user.language_code || "").trim() || null;
    const isPremium = user.is_premium === true;

    await pool.query(
      `
      INSERT INTO users (user_id, username, tz, created_at, language_code, is_premium, first_name)
      VALUES ($1, $2, 'UTC', NOW(), $3, $4, $5)
      ON CONFLICT (user_id)
      DO UPDATE SET
        username      = COALESCE(EXCLUDED.username, users.username),
        first_name    = COALESCE(EXCLUDED.first_name, users.first_name),
        language_code = COALESCE(EXCLUDED.language_code, users.language_code),
        is_premium    = EXCLUDED.is_premium
      `,
      [userId, username, langCode, isPremium, firstName]
    );
  } catch (e) {
    console.log("[USER_UPSERT] failed:", e?.message || e);
  }
}

// Диагностика подключения к БД
app.post('/api/debug/db_check', async (req, res) => {
  try {
    // Проверяем подключение к БД
    const result = await pool.query('SELECT NOW() as current_time');
    console.log('[DEBUG] PostgreSQL connection OK:', result.rows[0]);
    
    // Проверяем наличие таблиц
    const tables = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public'
    `);
    
    console.log('[DEBUG] Available tables:', tables.rows.map(r => r.table_name));
    
    res.json({
      ok: true,
      db_time: result.rows[0].current_time,
      tables: tables.rows.map(r => r.table_name)
    });
    
  } catch (error) {
    console.log('[DEBUG] DB check failed:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

// Диагностика конкретного розыгрыша
app.post('/api/debug/giveaway_check', async (req, res) => {
  try {
    const { gid } = req.body;
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    // 1. Проверяем сам розыгрыш
    const giveawayResult = await pool.query(
      'SELECT id, internal_title, status, end_at_utc FROM giveaways WHERE id = $1',
      [giveawayId]
    );

    // 2. Проверяем прикрепленные каналы
    const channelsResult = await pool.query(`
      SELECT gc.chat_id, gc.title, oc.username
      FROM giveaway_channels gc
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE gc.giveaway_id = $1
      ORDER BY gc.id
    `, [giveawayId]);

    res.json({
      ok: true,
      giveaway: giveawayResult.rows[0] || null,
      channels: channelsResult.rows,
      channels_count: channelsResult.rows.length
    });

  } catch (error) {
    console.log('[DEBUG] Giveaway check failed:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

// S3 Конфигурация
const S3_ENDPOINT = process.env.S3_ENDPOINT || 'https://s3.twcstorage.ru';
const S3_BUCKET = process.env.S3_BUCKET || '7b2a8ba5-prizeme-media';
const S3_KEY = process.env.S3_ACCESS_KEY || 'RRAW3NKI3GIRFXCF9BE0';
const S3_SECRET = process.env.S3_SECRET_KEY || 'jwEbCUdB68S8BJDBXWNSslMpcLeGmrm1e1A6iCzi';
const S3_REGION = process.env.S3_REGION || 'ru-1';
const MEDIA_BASE_URL = process.env.MEDIA_BASE_URL || 'https://media.prizeme.ru';

console.log('🔧 S3 Configuration Check:');
console.log('   S3_ENDPOINT:', S3_ENDPOINT);
console.log('   S3_BUCKET:', S3_BUCKET);
console.log('   S3_KEY:', S3_KEY ? '***SET***' : 'NOT SET');
console.log('   S3_SECRET:', S3_SECRET ? '***SET***' : 'NOT SET');
console.log('   S3_REGION:', S3_REGION);
console.log('   MEDIA_BASE_URL:', MEDIA_BASE_URL);

// Функция для создания подписи AWS Signature v4
function signS3Request(method, path, headers = {}) {
  const amzDate = new Date().toISOString().replace(/[:-]|\.\d{3}/g, '');
  const dateStamp = amzDate.slice(0, 8);
  
  // Канонический запрос
  const canonicalHeaders = `host:s3.twcstorage.ru\nx-amz-date:${amzDate}\n`;
  const signedHeaders = 'host;x-amz-date';
  const payloadHash = 'UNSIGNED-PAYLOAD';
  
  const canonicalRequest = `${method}\n${path}\n\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`;
  
  // Строка для подписи
  const algorithm = 'AWS4-HMAC-SHA256';
  const credentialScope = `${dateStamp}/${S3_REGION}/s3/aws4_request`;
  const stringToSign = `${algorithm}\n${amzDate}\n${credentialScope}\n${crypto.createHash('sha256').update(canonicalRequest).digest('hex')}`;
  
  // Подпись
  const kDate = crypto.createHmac('sha256', 'AWS4' + S3_SECRET).update(dateStamp).digest();
  const kRegion = crypto.createHmac('sha256', kDate).update(S3_REGION).digest();
  const kService = crypto.createHmac('sha256', kRegion).update('s3').digest();
  const kSigning = crypto.createHmac('sha256', kService).update('aws4_request').digest();
  const signature = crypto.createHmac('sha256', kSigning).update(stringToSign).digest('hex');
  
  return {
    'x-amz-date': amzDate,
    'x-amz-content-sha256': payloadHash,
    'Authorization': `${algorithm} Credential=${S3_KEY}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`
  };
}

app.get('/uploads/:path(*)', async (req, res) => {
  try {
    const mediaPath = req.params.path;
    console.log(`[MEDIA] Request for: ${mediaPath}`);
    
    const s3Path = `/${S3_BUCKET}/${mediaPath}`;
    const s3Url = `${S3_ENDPOINT}${s3Path}`;
    console.log(`[MEDIA] Proxying to: ${s3Url}`);
    
    // Создаем подписанный запрос
    const signedHeaders = signS3Request('GET', s3Path);
    
    const response = await fetch(s3Url, {
      method: 'GET',
      headers: {
        'Host': 's3.twcstorage.ru',
        ...signedHeaders
      }
    });

    if (!response.ok) {
      console.log(`[MEDIA] S3 response: ${response.status}`);
      return res.status(response.status).send('Media not found');
    }

    // Определяем MIME-тип
    let contentType = response.headers.get('content-type');
    if (!contentType) {
      const mimeType = mime.lookup(mediaPath);
      contentType = mimeType || 'application/octet-stream';
    }

    // Заголовки
    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'public, max-age=3600'); // Увеличиваем кэш
    res.setHeader('X-Proxy-From', s3Url);

    // Передаем данные потоком
    const buffer = await response.arrayBuffer();
    res.status(200).send(Buffer.from(buffer));

    console.log(`[MEDIA] ✅ Successfully served: ${mediaPath} (${contentType})`);

  } catch (error) {
    console.log(`[MEDIA] ❌ Error: ${error.message}`);
    res.status(500).send('Media proxy error');
  }
});


// УЛУЧШЕННЫЙ HEAD ЗАПРОС
app.head('/uploads/:path(*)', async (req, res) => {
  try {
    const mediaPath = req.params.path;
    const s3Path = `/${S3_BUCKET}/${mediaPath}`;
    const s3Url = `${S3_ENDPOINT}${s3Path}`;
    
    const signedHeaders = signS3Request('HEAD', s3Path);
    
    const response = await fetch(s3Url, { 
      method: 'HEAD',
      headers: {
        'Host': 's3.twcstorage.ru',
        ...signedHeaders
      },
      redirect: 'manual',
    });
    
    // ОБРАБОТКА РЕДИРЕКТОВ для HEAD
    let finalResponse = response;
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const redirectUrl = response.headers.get('location');
      if (redirectUrl) {
        finalResponse = await fetch(redirectUrl, { 
          method: 'HEAD',
          headers: {
            'Host': 's3.twcstorage.ru',
            ...signedHeaders
          }
        });
      }
    }
    
    const status = finalResponse.status < 400 ? 200 : 404;
    
    if (finalResponse.ok) {
      const contentType = finalResponse.headers.get('content-type') || mime.lookup(mediaPath) || 'application/octet-stream';
      res.setHeader('Content-Type', contentType);
      res.setHeader('Content-Length', finalResponse.headers.get('content-length') || '0');
      res.setHeader('Cache-Control', 'public, max-age=300');
    }
    
    res.status(status).end();
    
  } catch (error) {
    console.log(`[MEDIA-HEAD] Error: ${error.message}`);
    res.status(500).end();
  }
});


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

function convertUTCtoMSK(utcDateString) {
    try {
        if (!utcDateString) return null;
        
        // Создаем дату из UTC строки
        const utcDate = new Date(utcDateString);
        if (isNaN(utcDate.getTime())) return null;
        
        // MSK = UTC+3
        const mskDate = new Date(utcDate.getTime() + (3 * 60 * 60 * 1000));
        return mskDate;
    } catch (error) {
        console.log(`[TIMEZONE] Error converting UTC to MSK: ${error}`);
        return null;
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
      } else if (description.toLowerCase().includes('bad request: user not found') || 
                 description.toLowerCase().includes('participant_id_invalid')) {
        // PARTICIPANT_ID_INVALID - пользователь не существует в Telegram
        return { ok: false, debug: 'participant_id_invalid', status: 'invalid' };
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

let _cachedBotUsername = null;

// --- GET /api/bot_username ---
app.get('/api/bot_username', async (req, res) => {
  try {
    if (_cachedBotUsername) {
      return res.json({ ok: true, username: _cachedBotUsername });
    }
    if (!BOT_TOKEN) return res.status(500).json({ ok: false, reason: 'no_bot_token' });

    const r = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getMe`, { timeout: 8000 });
    const data = await r.json();

    if (!data.ok || !data.result?.username) {
      return res.status(500).json({ ok: false, reason: 'getMe_failed' });
    }

    _cachedBotUsername = data.result.username;
    return res.json({ ok: true, username: _cachedBotUsername });
  } catch (e) {
    console.error('[API bot_username] error:', e);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});


// Serve static files from webapp directory
app.use('/miniapp-static', express.static(path.join(__dirname, '../webapp'), {
    etag: false,
    lastModified: false,
    setHeaders: (res, filePath) => {
        if (filePath.endsWith('.js') || filePath.endsWith('.css')) {
            res.setHeader('Cache-Control', 'no-store');
        }
    }
}));

// HTML endpoints for Mini App
app.get('/miniapp/', (req, res) => {
  const tgWebAppStartParam = req.query.tgWebAppStartParam;
  console.log('🎯 [ROOT] Request to /miniapp/, tgWebAppStartParam:', tgWebAppStartParam);

  // Если нет параметра розыгрыша — просто отдаём index.html (БЕЗ redirect)
  if (!tgWebAppStartParam || tgWebAppStartParam === 'demo') {
    console.log('ℹ️ [ROOT] No valid start param, serving index.html');
    return res.sendFile(path.join(__dirname, '../webapp/index.html'));
  }

  // PAGE REDIRECT: параметры page_* — навигация в SPA, не gid розыгрыша.
  // Сохраняем в sessionStorage и отдаём index.html напрямую.
  if (String(tgWebAppStartParam).startsWith('page_')) {
    console.log('🗺️ [ROOT] Page navigation param detected, serving index.html directly:', tgWebAppStartParam);
    const pageParam = String(tgWebAppStartParam).replace(/'/g, "\\'");
    return res.send(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8" />
        <title>PrizeMe</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script>
          (function () {
            try {
              var tg = window.Telegram && Telegram.WebApp;
              if (tg && tg.initData) {
                sessionStorage.setItem('prizeme_init_data', tg.initData);
              }
              if (tg) {
                try { tg.requestFullscreen(); } catch (e) {}
                try { tg.expand(); } catch (e) {}
              }
            } catch (e) {}
            try {
              sessionStorage.setItem('prizeme_page_param', '${pageParam}');
            } catch (e) {}
            window.location.replace('/miniapp/index');
          })();
        </script>
      </head>
      <body></body>
      </html>
    `);
  }

  const gid = String(tgWebAppStartParam).replace(/'/g, "\\'");

  // Если параметр есть — отдаем маленькую страницу, которая сохраняет initData+gid
  // и делает replace на /miniapp/loading (replace = без истории, меньше шансов на циклы)
  return res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>PrizeMe - Loading</title>
      <script src="https://telegram.org/js/telegram-web-app.js"></script>
      <script>
        (function () {
          try {
            var tg = window.Telegram && Telegram.WebApp;
            if (tg && tg.initData) {
              sessionStorage.setItem('prizeme_init_data', tg.initData);
            }
          } catch (e) {}

          try {
            sessionStorage.setItem('prizeme_gid', '${gid}');
          } catch (e) {}

          // Важно: replace, не href
          window.location.replace('/miniapp/loading?gid=${gid}');
        })();
      </script>
    </head>
    <body></body>
    </html>
  `);
});

app.get('/miniapp/loading', (req, res) => {
  res.sendFile(path.join(__dirname, '../webapp/loading.html'));
});

app.get('/miniapp/need_subscription', (req, res) => {
  res.sendFile(path.join(__dirname, '../webapp/need_subscription.html'));
});

app.get('/miniapp/success', (req, res) => {
  res.sendFile(path.join(__dirname, '../webapp/success.html'));
});

app.get('/miniapp/already', (req, res) => {
  res.sendFile(path.join(__dirname, '../webapp/already_participating.html'));
});

// Экран результатов для победителя
app.get('/miniapp/results_win', (req, res) => {
  const winPath = path.join(__dirname, '../webapp/results_win.html');
  if (fs.existsSync(winPath)) {
    res.sendFile(winPath);
  } else {
    res.status(404).send('<h1>Экран результатов (победа) временно недоступен</h1>');
  }
});

// Экран результатов для НЕ победителя
app.get('/miniapp/results_lose', (req, res) => {
  const losePath = path.join(__dirname, '../webapp/results_lose.html');
  if (fs.existsSync(losePath)) {
    res.sendFile(losePath);
  } else {
    res.status(404).send('<h1>Экран результатов (участие) временно недоступен</h1>');
  }
});

app.get('/miniapp/results_no_participant', (req, res) => {
  const p = path.join(__dirname, '../webapp/results_no_participant.html');
  if (fs.existsSync(p)) {
    res.sendFile(p);
  } else {
    res.status(404).send('<h1>Экран недоступен</h1>');
  }
});

app.get('/miniapp/robokassa_pay', (req, res) => {
    const p = path.join(__dirname, '../webapp/robokassa_pay.html');
    if (fs.existsSync(p)) {
        res.sendFile(p);
    } else {
        res.status(404).send('<h1>Страница оплаты недоступна</h1>');
    }
});

// Participant and creator home pages
app.get('/miniapp/index', (req, res) => {
  res.sendFile(path.join(__dirname, '../webapp/index.html'));
});

// HEAD ENDPOINTS

// HEAD для всех miniapp routes
app.head('/miniapp/*', (req, res) => {
  res.status(200).end();
});

// HEAD для health check
app.head('/health', (req, res) => {
  res.status(200).end();
});

// HEAD для статических файлов
app.head('/miniapp-static/*', (req, res) => {
  res.status(200).end();
});

// HEAD для API endpoints (важно для Telegram)
app.head('/api/*', (req, res) => {
  res.status(200).end();
});


// --- POST /api/check_giveaway_status ---
app.post('/api/check_giveaway_status', async (req, res) => {
  console.log('[CHECK_STATUS] Request received:', req.body);
  
  try {
    const { gid } = req.body;
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    // ЗАПРОС К POSTGRESQL
    const result = await pool.query(
      'SELECT status, end_at_utc FROM giveaways WHERE id = $1',
      [giveawayId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ ok: false, reason: 'giveaway_not_found' });
    }

    const row = result.rows[0];
    const status = row.status;
    const endAtUtc = row.end_at_utc;
    
    // Проверяем, завершен ли розыгрыш
    const isCompleted = ['completed', 'finished'].includes(status);

    console.log(`[CHECK_STATUS] gid=${giveawayId}, status=${status}, is_completed=${isCompleted}`);

    res.json({
      ok: true,
      status: status,
      end_at_utc: endAtUtc,
      is_completed: isCompleted
    });

  } catch (error) {
    console.log(`[CHECK_STATUS] Error: ${error}`);
    res.status(500).json({ ok: false, reason: `db_error: ${error.message}` });
  }
});

// ==========================================================
// Shared logic: membership check (optionally issue ticket)
// ==========================================================
async function checkGiveawayAccessAndMaybeTicket({ giveawayId, userId, issueTicket }) {
  // Получаем каналы розыгрыша из БД
  const channelsResult = await pool.query(`
    SELECT gc.chat_id, gc.title, oc.username
    FROM giveaway_channels gc
    LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
    WHERE gc.giveaway_id = $1
    ORDER BY gc.id
  `, [giveawayId]);

  const channels = channelsResult.rows.map(row => {
    const usernameClean = row.username ? row.username.replace(/^@/, '') : null;
    const url = usernameClean
      ? `https://t.me/${usernameClean}`
      : (row.chat_id ? `https://t.me/${row.chat_id}` : null);

    return {
      chat_id: row.chat_id,
      title: row.title,
      username: usernameClean,
      url
    };
  });

  // Получаем время окончания розыгрыша
  const giveawayResult = await pool.query(
    'SELECT end_at_utc FROM giveaways WHERE id = $1',
    [giveawayId]
  );
  const endAtUtc = giveawayResult.rows[0]?.end_at_utc || null;

  const details = [];

  if (!channels.length) {
    return {
      ok: true,
      done: false,
      need: [{ title: "Ошибка конфигурации", username: null, url: "#" }],
      details: ["No channels configured for this giveaway"],
      end_at_utc: endAtUtc,
      channels,
      ticket: null,
      is_new_ticket: false
    };
  }

  // Проверка подписки на каналы
  const need = [];
  let isOkOverall = true;

  for (const ch of channels) {
    const rawId = ch.chat_id;
    const title = ch.title || ch.username || "канал";
    const username = (ch.username || "").replace(/^@/, "") || null;

    let chatId = null;

    // Нормализация chat_id
    const { chatId: normalizedId, debug: normDebug } = _normalizeChatId(rawId, username);
    details.push(`[${title}] norm: ${normDebug}`);
    chatId = normalizedId;

    // Если не удалось нормализовать - пробуем резолв по username
    if (chatId === null && username) {
      try {
        const chatInfo = await tgGetChat(username);
        chatId = parseInt(chatInfo.id);
        details.push(`[${title}] resolved id=${chatId} from @${username}`);
      } catch (error) {
        details.push(`[${title}] resolve_failed: ${error.message}`);
      }
    }

    // Если chatId так и не появился - используем raw_id
    if (chatId === null && rawId) {
      chatId = rawId;
      details.push(`[${title}] using_raw_id: ${rawId}`);
    }

    // Проверка членства
    let channelOk = false;
    let participantInvalid = false;

    try {
      if (chatId && await _isMemberLocal(parseInt(chatId), parseInt(userId))) {
        details.push(`[${title}] local=OK`);
        channelOk = true;
      } else {
        const memberResult = await tgGetChatMember(parseInt(chatId), parseInt(userId));
        details.push(`[${title}] ${memberResult.debug}`);

        if (memberResult.status === 'invalid') {
          // Пользователь не существует в Telegram - особая обработка
          details.push(`[${title}] participant_id_invalid - user does not exist in Telegram`);
          channelOk = false;
          participantInvalid = true;
          need.push({
            title: title,
            username: username,
            url: username ? `https://t.me/${username}` : `https://t.me/${chatId}`,
            error: 'user_not_found'
          });
        } else if (['creator', 'administrator', 'member'].includes(memberResult.status)) {
          channelOk = true;
        } else {
          channelOk = false;
          need.push({
            title: title,
            username: username,
            url: username ? `https://t.me/${username}` : `https://t.me/${chatId}`
          });
        }
      }
    } catch (error) {
      details.push(`[${title}] get_chat_member_failed: ${error.message}`);
      channelOk = false;
      need.push({
        title: title,
        username: username,
        url: username ? `https://t.me/${username}` : `https://t.me/${chatId}`
      });
    }

    if (!channelOk && !participantInvalid) {
      isOkOverall = false;
    }
  }

  const done = isOkOverall;

  // Записываем клик (уникальный — один раз на пользователя на розыгрыш)
  try {
    await pool.query(
      `INSERT INTO giveaway_clicks (giveaway_id, user_id)
       VALUES ($1, $2)
       ON CONFLICT (giveaway_id, user_id) DO NOTHING`,
      [giveawayId, userId]
    );
  } catch (_e) { console.log('[CLICK] insert failed:', _e.message); }

  // Записываем pending_subscriptions для каналов где НЕ подписан (для трекинга новых подписчиков)
  if (!done) {
    for (const n of need) {
      try {
        await pool.query(
          `INSERT INTO pending_subscriptions (giveaway_id, user_id, channel_id)
           VALUES ($1, $2, $3)
           ON CONFLICT (giveaway_id, user_id, channel_id) DO NOTHING`,
          [giveawayId, userId, n.chat_id || channels.find(c => c.title === n.title)?.chat_id]
        );
      } catch (_e) { console.log('[PENDING_SUB] insert failed:', _e.message); }
    }
  }

  // Если нельзя выдавать билет — возвращаем только проверки
  if (!issueTicket) {
    return {
      ok: true,
      done,
      need,
      details,
      end_at_utc: endAtUtc,
      channels,
      ticket: null,
      is_new_ticket: false
    };
  }

  // Иначе — работаем с билетом (как было раньше)
  let ticket = null;
  let isNewTicket = false;

  if (done) {
    // 1) Ищем существующий билет
    const ticketResult = await pool.query(
      'SELECT ticket_code FROM entries WHERE giveaway_id = $1 AND user_id = $2',
      [giveawayId, userId]
    );

    if (ticketResult.rows.length > 0) {
      ticket = ticketResult.rows[0].ticket_code;
      details.push('ticket_found');
    } else {
      // 2) Создаем новый билет
      const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
      for (let attempt = 0; attempt < 8; attempt++) {
        const code = Array.from({ length: 6 }, () =>
          alphabet[Math.floor(Math.random() * alphabet.length)]
        ).join('');

        try {
          const srcChannelId = channels.length > 0 ? channels[0].chat_id : null;
          const entryRes = await pool.query(
            `INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at, source_channel_id)
             VALUES ($1, $2, $3, true, NOW(), $4) RETURNING id`,
            [giveawayId, userId, code, srcChannelId]
          );
          ticket = code;
          isNewTicket = true;
          // Записываем entry_subscriptions — was_subscribed=false если был в pending
          const entryId = entryRes.rows[0]?.id;
          if (entryId) {
            // Проверяем кто был в pending (не был подписан при первом нажатии)
            const pendingRes = await pool.query(
              `SELECT channel_id FROM pending_subscriptions
               WHERE giveaway_id=$1 AND user_id=$2`,
              [giveawayId, userId]
            );
            const pendingChannels = new Set(pendingRes.rows.map(r => String(r.channel_id)));

            for (const ch of channels) {
              const wasSub = !pendingChannels.has(String(ch.chat_id));
              try {
                await pool.query(
                  `INSERT INTO entry_subscriptions
                     (entry_id, giveaway_id, user_id, channel_id, was_subscribed)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT DO NOTHING`,
                  [entryId, giveawayId, userId, ch.chat_id, wasSub]
                );
              } catch (_e) { console.log('[ENTRY_SUB] failed:', _e.message); }
            }
          }
          details.push(`ticket_created_attempt_${attempt + 1}`);
          // Уведомляем бота для публикации в PRIME
          try {
            await fetch(`${BOT_INTERNAL_URL}/internal/notify_prime`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ giveaway_id: giveawayId })
            });
          } catch (_e) { console.log('[PRIME] notify failed:', _e.message); }
          break;
        } catch (error) {
          if (error.code === '23505') {
            details.push(`ticket_collision_${code}`);
            continue;
          }
          details.push(`ticket_issue_error: ${error.message}`);
          break;
        }
      }
    }
  }

  return {
    ok: true,
    done,
    need,
    details,
    end_at_utc: endAtUtc,
    channels,
    ticket,
    is_new_ticket: isNewTicket
  };
}

// --- POST /api/check_membership_only ---
// НИКОГДА не выдает билет. Только проверяет подписки/условия.
app.post('/api/check_membership_only', async (req, res) => {
  console.log('[CHECK_MEMBERSHIP_ONLY] Request received:', req.body);

  if (!BOT_TOKEN) {
    return res.status(500).json({ ok: false, reason: 'no_bot_token' });
  }

  try {
    const { gid, init_data } = req.body;
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    await upsertMiniAppUser(parsedInitData.user_parsed);

    const userId = parseInt(parsedInitData.user_parsed.id);
    console.log(`[CHECK_MEMBERSHIP_ONLY] user_id=${userId}, gid=${giveawayId}`);

    const result = await checkGiveawayAccessAndMaybeTicket({
      giveawayId,
      userId,
      issueTicket: false
    });

    // Возвращаем "чистый" ответ без ticket
    return res.json({
      ok: true,
      done: result.done,
      need: result.need || [],
      end_at_utc: result.end_at_utc || null,
      details: result.details || [],
      channels: result.channels || []
    });

  } catch (error) {
    console.log(`[CHECK_MEMBERSHIP_ONLY] Error: ${error}`);
    return res.status(500).json({ ok: false, reason: `server_error: ${error.message}` });
  }
});


// --- POST /api/check ---
app.post('/api/check', async (req, res) => {
  console.log('[CHECK] Request received:', req.body);

  if (!BOT_TOKEN) {
    return res.status(500).json({ ok: false, reason: 'no_bot_token' });
  }

  try {
    const { gid, init_data } = req.body;
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    // Валидация init_data и извлечение user_id
    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    await upsertMiniAppUser(parsedInitData.user_parsed);

    const userId = parseInt(parsedInitData.user_parsed.id);
    console.log(`[CHECK] user_id=${userId}, gid=${giveawayId}`);

    const result = await checkGiveawayAccessAndMaybeTicket({
      giveawayId,
      userId,
      issueTicket: true
    });

    // Важно: ok всегда true если сервер живой, done = выполнены условия
    return res.json({
      ok: true,
      done: result.done,
      need: result.need || [],
      ticket: result.ticket || null,
      is_new_ticket: !!result.is_new_ticket,
      end_at_utc: result.end_at_utc || null,
      details: result.details || [],
      channels: result.channels || []
    });

  } catch (error) {
    console.log(`[CHECK] Error: ${error}`);
    return res.status(500).json({ ok: false, reason: `server_error: ${error.message}` });
  }
});


// --- POST /api/claim ---
app.post('/api/claim', async (req, res) => {
  console.log('[CLAIM] Request received:', req.body);

  if (!BOT_TOKEN) {
    return res.status(500).json({ ok: false, reason: 'no_bot_token' });
  }

  try {
    const { gid, init_data } = req.body;
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    // Валидация init_data и извлечение user_id
    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    await upsertMiniAppUser(parsedInitData.user_parsed);

    const userId = parseInt(parsedInitData.user_parsed.id);
    console.log(`[CLAIM] user_id=${userId}, gid=${giveawayId}`);

    // Получаем время окончания розыгрыша
    const giveawayResult = await pool.query(
      'SELECT end_at_utc FROM giveaways WHERE id = $1',
      [giveawayId]
    );
    const endAtUtc = giveawayResult.rows[0]?.end_at_utc || null;

    // Проверяем есть ли уже билет ПРЕЖДЕ проверки подписки
    const existingTicket = await pool.query(
      'SELECT ticket_code FROM entries WHERE giveaway_id = $1 AND user_id = $2',
      [giveawayId, userId]
    );

    if (existingTicket.rows.length > 0) {
      console.log(`[CLAIM] ✅ Пользователь уже имеет билет: ${existingTicket.rows[0].ticket_code}`);
      return res.json({
        ok: true,
        done: true,
        ticket: existingTicket.rows[0].ticket_code,
        end_at_utc: endAtUtc,
        details: ["Already have ticket - skipping subscription check"]
      });
    }

    // Проверка подписки на каналы
    const channelsResult = await pool.query(`
      SELECT gc.chat_id, gc.title, oc.username
      FROM giveaway_channels gc
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE gc.giveaway_id = $1
      ORDER BY gc.id
    `, [giveawayId]);

    const channels = channelsResult.rows.map(row => ({
      chat_id: row.chat_id,
      title: row.title,
      username: row.username
    }));

    const need = [];
    const details = [];

    for (const ch of channels) {
      const title = ch.title || "канал";
      const username = (ch.username || "").replace(/^@/, "") || null;
      
      try {
        const chatId = parseInt(ch.chat_id);
        
        // Проверка членства
        let isOk = false;
        if (await _isMemberLocal(chatId, userId)) {
          isOk = true;
        } else {
          const memberResult = await tgGetChatMember(chatId, userId);
          details.push(`[${title}] ${memberResult.debug}`);
          isOk = memberResult.status !== 'invalid' && ['creator', 'administrator', 'member'].includes(memberResult.status);
        }

        if (!isOk) {
          need.push({
            title: title,
            username: username,
            url: username ? `https://t.me/${username}` : null
          });
        }
      } catch (error) {
        details.push(`[${title}] claim_check_failed: ${error.message}`);
        need.push({
          title: title,
          username: username,
          url: username ? `https://t.me/${username}` : null
        });
      }
    }

    const done = need.length === 0;
    if (!done) {
      return res.json({
        ok: true,
        done: false,
        need: need,
        end_at_utc: endAtUtc,
        details: details
      });
    }

    // Выдаем новый билет
    console.log(`[CLAIM] 📝 Создаем новый билет для user_id=${userId}, gid=${giveawayId}`);
    
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let ticket = null;

    for (let attempt = 0; attempt < 12; attempt++) {
      const code = Array.from({ length: 6 }, () => 
        alphabet[Math.floor(Math.random() * alphabet.length)]
      ).join('');
      
      try {
        const claimSrcRes = await pool.query(
          `SELECT chat_id FROM giveaway_channels WHERE giveaway_id = $1 ORDER BY id LIMIT 1`,
          [giveawayId]
        );
        const claimSrcId = claimSrcRes.rows[0]?.chat_id || null;
        const claimEntryRes = await pool.query(
          `INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at, source_channel_id)
           VALUES ($1, $2, $3, true, NOW(), $4) RETURNING id`,
          [giveawayId, userId, code, claimSrcId]
        );
        ticket = code;
        console.log(`[CLAIM] ✅ Успешно создан билет: ${code}`);
        // entry_subscriptions
        const claimEntryId = claimEntryRes.rows[0]?.id;
        if (claimEntryId) {
          const claimChRes = await pool.query(
            `SELECT chat_id FROM giveaway_channels WHERE giveaway_id = $1`, [giveawayId]
          );
          for (const ch of claimChRes.rows) {
            try {
              await pool.query(
                `INSERT INTO entry_subscriptions
                   (entry_id, giveaway_id, user_id, channel_id, was_subscribed)
                 VALUES ($1, $2, $3, $4, false)
                 ON CONFLICT DO NOTHING`,
                [claimEntryId, giveawayId, userId, ch.chat_id]
              );
            } catch (_e) {}
          }
        }
        // Уведомляем бота для публикации в PRIME
        try {
          await fetch(`${BOT_INTERNAL_URL}/internal/notify_prime`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ giveaway_id: giveawayId })
          });
        } catch (_e) { console.log('[PRIME] notify failed:', _e.message); }
        break;
      } catch (error) {
        if (error.code === '23505') { // UNIQUE constraint violation
          console.log(`[CLAIM] ⚠️ Коллизия билета ${code}, попытка ${attempt + 1}`);
          continue;
        } else {
          throw error;
        }
      }
    }

    if (!ticket) {
      console.log(`[CLAIM] ❌ Не удалось создать уникальный билет после 12 попыток`);
      return res.status(500).json({
        ok: false,
        done: true,
        reason: "ticket_issue_failed_after_retries",
        end_at_utc: endAtUtc
      });
    }

    res.json({
      ok: true,
      done: true,
      ticket: ticket,
      end_at_utc: endAtUtc,
      details: details
    });

  } catch (error) {
    console.log(`[CLAIM] ❌ Критическая ошибка: ${error}`);
    res.status(500).json({ 
      ok: false, 
      reason: `server_error: ${error.message}`
    });
  }
});

// --- POST /api/results ---
app.post('/api/results', async (req, res) => {
  console.log('[RESULTS] Request received:', req.body);
  
  try {
    const { gid, init_data } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    await upsertMiniAppUser(parsedInitData.user_parsed);

    const userId = parseInt(parsedInitData.user_parsed.id);
    const giveawayId = parseInt(gid);

    if (!giveawayId) {
      return res.status(400).json({ ok: false, reason: 'bad_gid' });
    }

    console.log(`[RESULTS] USER_EXTRACTED: id=${userId}, gid=${giveawayId}`);

    // 🔧 ПРОВЕРЯЕМ СТАТУС РОЗЫГРЫША
    const statusCheck = await pool.query(
      'SELECT status FROM giveaways WHERE id = $1',
      [giveawayId]
    );
    
    if (statusCheck.rows.length === 0) {
      return res.json({ ok: false, reason: 'giveaway_not_found' });
    }
    
    const giveawayStatus = statusCheck.rows[0].status;
    console.log(`[RESULTS] Giveaway status: ${giveawayStatus}`);
    
    // 🔧 ЕСЛИ РОЗЫГРЫШ ЕЩЕ НЕ ЗАВЕРШЕН - ВОЗВРАЩАЕМ СООБЩЕНИЕ
    if (!['completed', 'finished'].includes(giveawayStatus)) {
      return res.json({ 
        ok: true, 
        finished: false,
        message: "Розыгрыш еще не завершен. Результаты будут доступны после окончания."
      });
    }

    // Проксируем запрос к боту
    const response = await fetch(`${BOT_INTERNAL_URL}/api/giveaway_results`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        gid: giveawayId,
        user_id: userId
      }),
      timeout: 10000
    });

    if (response.ok) {
      const resultData = await response.json();
      
      // 🔧 ДОБАВЛЯЕМ ФЛАГ "НЕТ ПОБЕДИТЕЛЕЙ"
      if (resultData.winners && resultData.winners.length === 0) {
        resultData.noWinners = true;
        resultData.message = "Победителей в этом розыгрыше нет";
      }
      
      res.json(resultData);
    } else {
      console.log(`[RESULTS] Internal API error: ${response.status}`);
      res.status(500).json({ 
        ok: false, 
        reason: `internal_api_error: ${response.status}` 
      });
    }

  } catch (error) {
    console.log(`[RESULTS] Proxy error: ${error}`);
    res.status(500).json({ 
      ok: false, 
      reason: `proxy_error: ${error.message}` 
    });
  }
});

// --- POST /api/check_prime_status ---
// Возвращает PRIME-статус пользователя из таблицы bot_users
app.post('/api/check_prime_status', async (req, res) => {
  try {
    const { init_data } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId)) {
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });
    }

    const result = await pool.query(
      `SELECT is_prime FROM bot_users WHERE user_id = $1`,
      [userId]
    );

    // Если пользователя нет в bot_users — считаем не-PRIME (он ещё не открывал бота)
    const isPrime = result.rows.length > 0 ? result.rows[0].is_prime : false;

    console.log(`[API check_prime_status] user_id=${userId}, is_prime=${isPrime}`);

    return res.json({ ok: true, is_prime: isPrime });

  } catch (error) {
    console.error('[API check_prime_status] error:', error);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// --- POST /api/participant_home_giveaways ---
// Отдает списки розыгрышей для главной страницы участника:
//   top    — розыгрыши с активным платным размещением в топе (top_placements)
//            фоллбек: последние 5 активных, если платных размещений нет
//   latest — все текущие активные розыгрыши (для PRIME-пользователей)
app.post('/api/participant_home_giveaways', async (req, res) => {
  try {
    const LIMIT_TOP    = 5;
    const LIMIT_LATEST = 100;

    // ── Вспомогательный маппер строки БД → объект для фронта ──────────────
    const mapRow = (row) => {
      // Строим channels_meta: [{title, avatar_url, post_url}] для каждого канала
      const channelsMeta = (row.channels_raw || [])
        .filter(ch => ch && ch.title)
        .map(ch => {
          const messageId = ch.message_id ? Number(ch.message_id) : null;
          let postUrl = null;

          if (messageId) {
            if (ch.username) {
              // Публичный канал: t.me/username/message_id
              postUrl = `https://t.me/${ch.username}/${messageId}`;
            } else if (ch.chat_id) {
              // Приватный канал: t.me/c/<internal_id>/<message_id>
              const internal = String(ch.chat_id).replace(/^-100/, '');
              postUrl = `https://t.me/c/${internal}/${messageId}`;
            }
          }

          return {
            title:      ch.title || ch.username || 'Канал',
            avatar_url: ch.chat_id ? `/api/chat_avatar/${ch.chat_id}` : null,
            post_url:   postUrl,
          };
        });

      return {
        id:                      row.id,
        title:                   row.internal_title,
        public_description:      row.public_description,
        end_at_utc:              row.end_at_utc,
        status:                  row.status,
        channels:                row.channels || [],
        channels_meta:           channelsMeta,
        first_channel_avatar_url: row.first_channel_chat_id
          ? `/api/chat_avatar/${row.first_channel_chat_id}`
          : null,
        participants_count: row.participants_count
          ? Number(row.participants_count)
          : 0,
      };
    };

    // ── Общая SELECT-часть (переиспользуется в обоих запросах) ────────────
    const SELECT_GIVEAWAY = `
      SELECT
        g.id,
        g.internal_title,
        g.public_description,
        g.end_at_utc,
        g.status,
        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,
        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id,
        (
          SELECT COUNT(DISTINCT e.user_id)
          FROM entries e
          WHERE e.giveaway_id = g.id
        ) AS participants_count,
        json_agg(
          json_build_object(
            'title',      COALESCE(gc.title, oc.title, oc.username),
            'username',   oc.username,
            'chat_id',    gc.chat_id,
            'message_id', gc.message_id,
            'is_private', CASE WHEN oc.username IS NULL THEN true ELSE false END
          )
          ORDER BY gc.id
        ) AS channels_raw
      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
    `;

    // ── Запрос 1: платные топ-размещения ─────────────────────────────────
    // Берём только те розыгрыши, у которых есть активная запись в top_placements
    // (is_active = true И ends_at ещё не истёк)
    const topPaidResult = await pool.query(`
      ${SELECT_GIVEAWAY}
      INNER JOIN top_placements tp
        ON tp.giveaway_id = g.id
        AND tp.is_active  = true
        AND tp.ends_at    > NOW()
      WHERE g.status = 'active'
      GROUP BY g.id, tp.starts_at
      ORDER BY tp.starts_at ASC
      LIMIT $1
    `, [LIMIT_TOP]);

    // ── Запрос 2: все активные розыгрыши (для каталога PRIME) ────────────
    // Показываем только розыгрыши с 3+ участниками
    const latestResult = await pool.query(`
      ${SELECT_GIVEAWAY}
      WHERE g.status = 'active'
        AND (
          SELECT COUNT(DISTINCT e.user_id) FROM entries e
          WHERE e.giveaway_id = g.id AND e.prelim_ok = true
        ) >= 3
      GROUP BY g.id
      ORDER BY g.id DESC
      LIMIT $1
    `, [LIMIT_LATEST]);

    const topPaid  = (topPaidResult.rows  || []).map(mapRow);
    const latest   = (latestResult.rows   || []).map(mapRow);

    // Топ — только платные размещения, без фоллбека
    const top = topPaid;

    res.json({
      ok:                 true,
      top,
      latest,
      total_latest_count: latest.length,
    });

  } catch (error) {
    console.error('[API participant_home_giveaways] error:', error);
    res.status(500).json({
      ok:     false,
      reason: 'server_error: ' + error.message,
    });
  }
});

// --- GET /api/chat_avatar/:chatId ---
// Отдает ПРЯМУЮ ссылку на файл аватара Telegram-канала
app.get('/api/chat_avatar/:chatId', async (req, res) => {
    try {
        const { chatId } = req.params;
        const fallbackMode = String(req.query.fallback || 'default'); // 'default' | 'none'
        const noFallback = fallbackMode === 'none';

        console.log(`[API chat_avatar] Request for chat_id: ${chatId}`);

        const telegramChatId = parseInt(chatId);
        if (!telegramChatId || !BOT_TOKEN) {
            // Если что-то не так, возвращаем заглушку через наш прокси
            if (noFallback) return res.status(404).end();
            return res.redirect('/uploads/avatars/default_channel.png');
        }

        // 1. Запрашиваем информацию о чате
        const tgResponse = await fetch(
            `https://api.telegram.org/bot${BOT_TOKEN}/getChat?chat_id=${telegramChatId}`,
            { timeout: 5000 }
        );

        const data = await tgResponse.json();
        if (!data.ok || !data.result.photo) {
            // Если аватар не найден, редиректим на заглушку
            if (noFallback) return res.status(404).end();
            return res.redirect('/uploads/avatars/default_channel.png');
        }

        // 2. Получаем file_id аватара
        const fileId = data.result.photo.big_file_id;
        // 3. Запрашиваем путь к файлу у Telegram
        const fileResponse = await fetch(
            `https://api.telegram.org/bot${BOT_TOKEN}/getFile?file_id=${fileId}`,
            { timeout: 5000 }
        );

        const fileData = await fileResponse.json();
        if (!fileData.ok) {
            if (noFallback) return res.status(404).end();
            return res.redirect('/uploads/avatars/default_channel.png');
        }

        const filePath = fileData.result.file_path;
        // 4. Формируем прямую ссылку на файл в Telegram
        const directAvatarUrl = `https://api.telegram.org/file/bot${BOT_TOKEN}/${filePath}`;

        console.log(`[API chat_avatar] Redirecting to direct URL for ${chatId}`);
        // 5. Перенаправляем браузер на загрузку аватара
        res.redirect(directAvatarUrl);

    } catch (error) {
      console.error(`[API chat_avatar] Error for ${req.params.chatId}:`, error);
      // ✅ Важно: если просили fallback=none — возвращаем 404, чтобы фронт показал букву
      if (noFallback) return res.status(404).end();
      return res.redirect('/uploads/avatars/default_channel.png');
    }
});

// --- GET /api/giveaway_media/:giveawayId ---
// Отдает ПРЯМУЮ ссылку на медиа розыгрыша (photo_file_id) через Telegram getFile
app.get('/api/giveaway_media/:giveawayId', async (req, res) => {
  try {
    const giveawayId = parseInt(req.params.giveawayId, 10);
    if (!giveawayId || !BOT_TOKEN) {
      return res.status(404).end();
    }

    // Берем file_id из БД
    const r = await pool.query(
      `SELECT photo_file_id FROM giveaways WHERE id = $1 LIMIT 1`,
      [giveawayId]
    );

    const photoFileIdRaw = r.rows?.[0]?.photo_file_id;
    if (!photoFileIdRaw) {
      return res.status(404).end();
    }

    // В БД хранится строка вида: "photo:<file_id>"
    const parts = String(photoFileIdRaw).split(':');
    const fileId = parts.length > 1 ? parts.slice(1).join(':') : parts[0];

    if (!fileId) {
      return res.status(404).end();
    }

    // Запрашиваем путь к файлу у Telegram
    const fileResponse = await fetch(
      `https://api.telegram.org/bot${BOT_TOKEN}/getFile?file_id=${fileId}`,
      { timeout: 8000 }
    );

    const fileData = await fileResponse.json();
    if (!fileData.ok || !fileData.result?.file_path) {
      return res.status(404).end();
    }

    const filePath = fileData.result.file_path;
    const directUrl = `https://api.telegram.org/file/bot${BOT_TOKEN}/${filePath}`;

    // Редиректим на прямую ссылку
    return res.redirect(directUrl);

  } catch (error) {
    console.error('[API giveaway_media] error:', error);
    return res.status(500).end();
  }
});


// --- POST /api/creator_total_giveaways ---
// Возвращает общее кол-во розыгрышей, созданных текущим создателем
app.post('/api/creator_total_giveaways', async (req, res) => {
  try {
    const { init_data } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId)) {
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });
    }

    const result = await pool.query(
      `
        SELECT COUNT(*)::int AS total
        FROM giveaways
        WHERE owner_user_id = $1
      `,
      [userId]
    );

    const total = result.rows[0]?.total ?? 0;

    console.log(`[API creator_total_giveaways] owner_user_id=${userId}, total=${total}`);

    return res.json({
      ok: true,
      total_giveaways: total,
    });

  } catch (error) {
    console.error('[API creator_total_giveaways] error:', error);
    return res.status(500).json({
      ok: false,
      reason: 'server_error',
      error: error.message
    });
  }
});

// --- POST /api/creator_giveaways ---
// Отдает список розыгрышей создателя по статусу (active/draft/completed)
app.post('/api/creator_giveaways', async (req, res) => {
  try {
    const { init_data, status } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId)) {
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });
    }

    // status bucket
    let whereStatusSql = '';
    if (status === 'active') {
      whereStatusSql = `AND g.status = 'active'`;
    } else if (status === 'completed') {
      whereStatusSql = `AND g.status IN ('completed','finished')`;
    } else {
      // "draft" bucket = все, что не active и не completed/finished
      whereStatusSql = `AND g.status NOT IN ('active','completed','finished')`;
    }

    const result = await pool.query(`
      SELECT
        g.id,
        g.internal_title,
        g.end_at_utc,
        g.status,

        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,

        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id

      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id

      WHERE g.owner_user_id = $1
      ${whereStatusSql}

      GROUP BY g.id
      ORDER BY g.id DESC
    `, [userId]);

    const rows = result.rows || [];

    const items = rows.map(row => {
      const firstChatId = row.first_channel_chat_id || null;
      return {
        id: row.id,
        title: row.internal_title,
        end_at_utc: row.end_at_utc,
        status: row.status,
        channels: row.channels || [],
        first_channel_avatar_url: firstChatId ? `/api/chat_avatar/${firstChatId}` : null,
      };
    });

    return res.json({
      ok: true,
      total: items.length,
      items
    });

  } catch (error) {
    console.error('[API creator_giveaways] error:', error);
    return res.status(500).json({
      ok: false,
      reason: 'server_error',
      error: error.message
    });
  }
});

// --- POST /api/create_stars_invoice ---
// Создаёт Telegram Stars инвойс через бота и возвращает invoice_link.
app.post('/api/create_stars_invoice', async (req, res) => {
    try {
        const { init_data, giveaway_id, period, stars } = req.body;
        console.log('[API create_stars_invoice] body:', { giveaway_id, period, stars });

        const parsedInitData = _tgCheckMiniAppInitData(init_data);
        if (!parsedInitData || !parsedInitData.user_parsed) {
            return res.status(400).json({ ok: false, reason: 'bad_initdata' });
        }

        const userId = Number(parsedInitData.user_parsed.id);
        if (!Number.isFinite(userId)) {
            return res.status(400).json({ ok: false, reason: 'bad_user_id' });
        }

        // Валидация периода
        const VALID_PERIODS = { day: 150, week: 450 };
        if (!VALID_PERIODS[period]) {
            return res.status(400).json({ ok: false, reason: 'invalid_period' });
        }

        // Проверяем что rosa принадлежит этому пользователю
        const gw = await pool.query(
            `SELECT id, internal_title FROM giveaways
             WHERE id = $1 AND owner_user_id = $2 AND status = 'active'`,
            [giveaway_id, userId]
        );
        if (!gw.rows.length) {
            return res.status(400).json({ ok: false, reason: 'giveaway_not_found' });
        }

        const giveawayTitle = gw.rows[0].internal_title;
        const starsAmount   = VALID_PERIODS[period];
        const periodLabel   = period === 'day' ? '1 день' : '1 неделю';

        // Создаём инвойс через Telegram Bot API
        const botToken = process.env.BOT_TOKEN;
        const invoiceResp = await fetch(
            `https://api.telegram.org/bot${botToken}/createInvoiceLink`,
            {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    title:           'Топ-розыгрыши',
                    description:     `Размещение «${giveawayTitle}» на ${periodLabel}`,
                    payload:         JSON.stringify({
                        type:        'top_placement',
                        giveaway_id: Number(giveaway_id),
                        period,
                        user_id:     userId,
                    }),
                    currency:        'XTR',
                    prices:          [{ label: `Топ на ${periodLabel}`, amount: starsAmount }],
                    provider_token:  '',
                }),
            }
        );

        const invoiceData = await invoiceResp.json();

        if (!invoiceData.ok) {
            console.error('[API create_stars_invoice] Telegram error:', invoiceData);
            return res.status(500).json({ ok: false, reason: 'telegram_api_error' });
        }

        return res.json({ ok: true, invoice_link: invoiceData.result });

    } catch (error) {
        console.error('[API create_stars_invoice] error:', error);
        return res.status(500).json({ ok: false, reason: 'server_error: ' + error.message });
    }
});

// --- POST /api/top_placement_checkout_data ---
// ── Robokassa: MD5 helper ─────────────────────────────────────────────────
function _roboMd5(str) {
    return crypto.createHash('md5').update(str).digest('hex').toUpperCase();
}

// --- POST /api/create_robokassa_invoice ---
app.post('/api/create_robokassa_invoice', async (req, res) => {
    try {
        const { init_data, giveaway_id, period, price_rub } = req.body;
        const parsedInitData = _tgCheckMiniAppInitData(init_data);
        if (!parsedInitData?.user_parsed) {
            return res.status(400).json({ ok: false, reason: 'bad_initdata' });
        }
        const userId = Number(parsedInitData.user_parsed.id);

        const VALID_PERIODS = { day: 149, week: 499 };
        if (!VALID_PERIODS[period]) {
            return res.status(400).json({ ok: false, reason: 'invalid_period' });
        }

        const gw = await pool.query(
            `SELECT id, internal_title FROM giveaways
             WHERE id = $1 AND owner_user_id = $2 AND status = 'active'`,
            [giveaway_id, userId]
        );
        if (!gw.rows.length) {
            return res.status(400).json({ ok: false, reason: 'giveaway_not_found' });
        }

        const giveawayTitle = gw.rows[0].internal_title;
        const outSum        = VALID_PERIODS[period].toFixed(2);
        const invId         = Date.now() * 1000 + (userId % 1000);
        const periodLabel   = period === 'day' ? '1 день' : '1 неделю';
        const description   = `Топ-размещение «${giveawayTitle}» на ${periodLabel}`;
        const p1            = ROBOKASSA_IS_TEST ? ROBOKASSA_TEST_PASSWORD1 : ROBOKASSA_PASSWORD1;
        const successUrl    = `https://t.me/${process.env.BOT_USERNAME || 'prizeme_bot'}?startapp=page_services`;
        const signature     = _roboMd5(`${ROBOKASSA_LOGIN}:${outSum}:${invId}:${p1}`);

        await pool.query(
            `INSERT INTO robokassa_orders (inv_id, giveaway_id, user_id, period, amount_rub, status)
             VALUES ($1, $2, $3, $4, $5, 'pending')`,
            [invId, giveaway_id, userId, period, outSum]
        );

        return res.json({
            ok: true,
            merchant_login: ROBOKASSA_LOGIN,
            out_sum:        outSum,
            inv_id:         invId,
            description,
            signature,
            is_test:        ROBOKASSA_IS_TEST,
            period:         period,
            price_rub:      outSum
        });
    } catch (e) {
        console.error('[ROBOKASSA] create_invoice error:', e);
        return res.status(500).json({ ok: false, reason: 'server_error' });
    }
});

// --- POST /api/create_promotion_robokassa_invoice ---
app.post('/api/create_promotion_robokassa_invoice', async (req, res) => {
    try {
        const { init_data, giveaway_id, publish_type, scheduled_at, price_rub } = req.body;
        const parsedInitData = _tgCheckMiniAppInitData(init_data);
        if (!parsedInitData?.user_parsed) {
            return res.json({ ok: false, reason: 'Unauthorized' });
        }
        const userId   = parsedInitData.user_parsed.id;
        const outSum   = parseFloat(price_rub || ROBOKASSA_PROMOTION_PRICE).toFixed(2);
        const invId    = Date.now() + userId % 10000;
        const p1       = ROBOKASSA_IS_TEST ? ROBOKASSA_TEST_PASSWORD1 : ROBOKASSA_PASSWORD1;
        const sig      = _roboMd5(`${ROBOKASSA_LOGIN}:${outSum}:${invId}:${p1}`);

        await pool.query(
            `INSERT INTO promotion_robokassa_orders
                (inv_id, user_id, giveaway_id, publish_type, scheduled_at, amount_rub, status)
             VALUES ($1, $2, $3, $4, $5, $6, 'pending')`,
            [invId, userId, giveaway_id, publish_type || 'immediate',
             scheduled_at || null, Math.round(parseFloat(outSum))]
        );

        return res.json({ ok: true, inv_id: invId });
    } catch (e) {
        console.error('[PROMO_ROBO] create invoice error:', e);
        return res.json({ ok: false, reason: e.message });
    }
});

// --- POST /api/robokassa_result (ResultURL от Robokassa) ---
app.post('/api/robokassa_result', express.urlencoded({ extended: false }), async (req, res) => {
    try {
        const { OutSum, InvId, SignatureValue } = req.body;
        console.log('[ROBOKASSA] result:', { OutSum, InvId, SignatureValue });

        // Проверяем подпись
        const p2       = ROBOKASSA_IS_TEST ? ROBOKASSA_TEST_PASSWORD2 : ROBOKASSA_PASSWORD2;
        const sig = String(SignatureValue).toUpperCase();
        const expected1 = _roboMd5(`${OutSum}:${InvId}:${p2}`);
        const expected2 = _roboMd5(`${parseFloat(OutSum).toFixed(2)}:${InvId}:${p2}`);
        if (expected1 !== sig && expected2 !== sig) {
            console.error('[ROBOKASSA] bad signature');
            return res.status(400).send('bad signature');
        }

        const invId = Number(InvId);

        // Проверяем оба типа заказов
        let order = await pool.query(
            `SELECT * FROM robokassa_orders WHERE inv_id = $1`, [invId]
        );

        // Если не top_placement — проверяем promotion
        if (!order.rows.length) {
            const promoOrder = await pool.query(
                `SELECT * FROM promotion_robokassa_orders WHERE inv_id = $1`, [invId]
            );
            if (!promoOrder.rows.length) {
                return res.status(400).send('order not found');
            }
            // Обрабатываем промо-заказ
            const o = promoOrder.rows[0];
            if (o.status !== 'pending') return res.send(`OK${invId}`);

            await pool.query(
                `UPDATE promotion_robokassa_orders SET status = 'paid', paid_at = NOW() WHERE inv_id = $1`,
                [invId]
            );
            try {
                await fetch(`${BOT_INTERNAL_URL}/internal/promotion_paid`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({
                        user_id:      o.user_id,
                        giveaway_id:  o.giveaway_id,
                        publish_type: o.publish_type,
                        scheduled_at: o.scheduled_at,
                        amount_rub:   o.amount_rub,
                        payment_type: 'card',
                    }),
                });
            } catch (_e) { console.log('[PROMO_ROBO] bot notify failed:', _e.message); }

            console.log(`[PROMO_ROBO] ✅ paid inv_id=${invId}`);
            return res.send(`OK${invId}`);
        }

        const o = order.rows[0];
        if (o.status !== 'pending') {
            // Уже обработан — идемпотентность
            return res.send(`OK${invId}`);
        }

        const periodDays  = o.period === 'day' ? 1 : 7;
        const periodLabel = o.period === 'day' ? '1 день' : '1 неделю';
        const startsAt    = new Date();
        const endsAt      = new Date(startsAt.getTime() + periodDays * 86400 * 1000);

        // Деактивируем предыдущий топ
        await pool.query(
            `UPDATE top_placements SET is_active = false
             WHERE giveaway_id = $1 AND is_active = true`,
            [o.giveaway_id]
        );

        // Создаём service_order
        const soRes = await pool.query(
            `INSERT INTO service_orders (giveaway_id, owner_user_id, service_type, price_rub, status, created_at)
             VALUES ($1, $2, 'top_placement', $3, 'paid', NOW()) RETURNING id`,
            [o.giveaway_id, o.user_id, Math.round(Number(o.amount_rub))]
        );
        const serviceOrderId = soRes.rows[0].id;

        // Создаём top_placement
        await pool.query(
            `INSERT INTO top_placements (giveaway_id, order_id, starts_at, ends_at, is_active, placement_type)
             VALUES ($1, $2, $3, $4, true, $5)`,
            [o.giveaway_id, serviceOrderId, startsAt, endsAt, o.period === 'day' ? 'day' : 'week']
        );

        // Обновляем статус заказа
        await pool.query(
            `UPDATE robokassa_orders SET status = 'paid', paid_at = NOW() WHERE inv_id = $1`,
            [invId]
        );

        // Уведомляем бота
        try {
            await fetch(`${BOT_INTERNAL_URL}/internal/top_placement_paid`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    user_id:     o.user_id,
                    giveaway_id: o.giveaway_id,
                    period:      o.period,
                    period_label: periodLabel,
                    payment_type: 'card'
                })
            });
        } catch (_e) { console.log('[ROBOKASSA] bot notify failed:', _e.message); }

        console.log(`[ROBOKASSA] ✅ paid inv_id=${invId}, gid=${o.giveaway_id}`);
        return res.send(`OK${invId}`);
    } catch (e) {
        console.error('[ROBOKASSA] result error:', e);
        return res.status(500).send('error');
    }
});

// --- POST /api/robokassa_promotion_result ---
app.post('/api/robokassa_promotion_result', express.urlencoded({ extended: false }), async (req, res) => {
    try {
        const { OutSum, InvId, SignatureValue } = req.body;
        console.log('[PROMO_ROBO] result:', { OutSum, InvId, SignatureValue });

        const p2  = ROBOKASSA_IS_TEST ? ROBOKASSA_TEST_PASSWORD2 : ROBOKASSA_PASSWORD2;
        const sig = String(SignatureValue).toUpperCase();
        const expected1 = _roboMd5(`${OutSum}:${InvId}:${p2}`);
        const expected2 = _roboMd5(`${parseFloat(OutSum).toFixed(2)}:${InvId}:${p2}`);
        if (expected1 !== sig && expected2 !== sig) {
            console.error('[PROMO_ROBO] bad signature');
            return res.status(400).send('bad signature');
        }

        const invId = Number(InvId);
        const order = await pool.query(
            `SELECT * FROM promotion_robokassa_orders WHERE inv_id = $1`, [invId]
        );
        if (!order.rows.length) return res.status(400).send('order not found');

        const o = order.rows[0];
        if (o.status !== 'pending') return res.send(`OK${invId}`);

        await pool.query(
            `UPDATE promotion_robokassa_orders SET status = 'paid', paid_at = NOW() WHERE inv_id = $1`,
            [invId]
        );

        // Уведомляем бота — он создаст bot_promotion запись и отправит уведомления
        try {
            await fetch(`${BOT_INTERNAL_URL}/internal/promotion_paid`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    user_id:      o.user_id,
                    giveaway_id:  o.giveaway_id,
                    publish_type: o.publish_type,
                    scheduled_at: o.scheduled_at,
                    amount_rub:   o.amount_rub,
                    payment_type: 'card',
                }),
            });
        } catch (_e) { console.log('[PROMO_ROBO] bot notify failed:', _e.message); }

        console.log(`[PROMO_ROBO] ✅ paid inv_id=${invId}`);
        return res.send(`OK${invId}`);
    } catch (e) {
        console.error('[PROMO_ROBO] result error:', e);
        return res.status(500).send('error');
    }
});

// --- GET /api/robokassa_order_status ---
app.get('/api/robokassa_order_status', async (req, res) => {
    try {
        const { inv_id } = req.query;
        if (!inv_id) {
            return res.status(400).json({ ok: false, reason: 'missing_inv_id' });
        }
        const order = await pool.query(
            `SELECT status FROM robokassa_orders WHERE inv_id = $1`, [Number(inv_id)]
        );
        if (!order.rows.length) {
            return res.json({ ok: true, status: 'not_found' });
        }
        return res.json({ ok: true, status: order.rows[0].status });
    } catch (e) {
        console.error('[ROBOKASSA] order_status error:', e);
        return res.status(500).json({ ok: false, reason: 'server_error' });
    }
});


// Отдаёт активные розыгрыши создателя для экрана чекаута топ-размещения.
// Исключает розыгрыши, которые уже в топе.
app.post('/api/top_placement_checkout_data', async (req, res) => {
  try {
    const { init_data } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId)) {
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });
    }

    const result = await pool.query(`
      SELECT
        g.id,
        g.internal_title,
        g.end_at_utc,
        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,
        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id
      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE g.owner_user_id = $1
        AND g.status = 'active'
        AND g.id NOT IN (
          SELECT giveaway_id FROM top_placements
          WHERE is_active = true AND ends_at > NOW()
        )
      GROUP BY g.id
      ORDER BY g.id DESC
    `, [userId]);

    return res.json({
      ok:    true,
      items: (result.rows || []).map(row => ({
        id:                    row.id,
        title:                 row.internal_title,
        end_at_utc:            row.end_at_utc,
        channels:              row.channels || [],
        first_channel_avatar_url: row.first_channel_chat_id
          ? `/api/chat_avatar/${row.first_channel_chat_id}`
          : null,
      })),
    });

  } catch (error) {
    console.error('[API top_placement_checkout_data] error:', error);
    return res.status(500).json({ ok: false, reason: 'server_error: ' + error.message });
  }
});

// --- POST /api/promotion_checkout_data ---
// Активные розыгрыши создателя для чекаута "Продвижение в боте"
app.post('/api/promotion_checkout_data', async (req, res) => {
  try {
    const { init_data } = req.body;
    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed)
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId))
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });

    const result = await pool.query(`
      SELECT
        g.id,
        g.internal_title,
        g.end_at_utc,
        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,
        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id
      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE g.owner_user_id = $1
        AND g.status = 'active'
      GROUP BY g.id
      ORDER BY g.id DESC
    `, [userId]);

    return res.json({
      ok: true,
      items: (result.rows || []).map(row => ({
        id:                       row.id,
        title:                    row.internal_title,
        end_at_utc:               row.end_at_utc,
        channels:                 row.channels || [],
        first_channel_avatar_url: row.first_channel_chat_id
          ? `/api/chat_avatar/${row.first_channel_chat_id}`
          : null,
      })),
    });
  } catch (error) {
    console.error('[API promotion_checkout_data] error:', error);
    return res.status(500).json({ ok: false, reason: 'server_error: ' + error.message });
  }
});

// --- POST /api/create_promotion_stars_invoice ---
// Создаёт Stars инвойс для сервиса "Продвижение в боте"
// ЦЕНА: константа, меняется в одном месте
const PROMOTION_PRICE_STARS = 9990; // ← меняй здесь

app.post('/api/create_promotion_stars_invoice', async (req, res) => {
  try {
    const { init_data, giveaway_id, publish_type, scheduled_at } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed)
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId))
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });

    if (!['immediate', 'scheduled'].includes(publish_type))
      return res.status(400).json({ ok: false, reason: 'invalid_publish_type' });

    if (publish_type === 'scheduled' && !scheduled_at)
      return res.status(400).json({ ok: false, reason: 'scheduled_at_required' });

    const gw = await pool.query(
      `SELECT id, internal_title FROM giveaways
       WHERE id = $1 AND owner_user_id = $2 AND status = 'active'`,
      [giveaway_id, userId]
    );
    if (!gw.rows.length)
      return res.status(400).json({ ok: false, reason: 'giveaway_not_found' });

    const giveawayTitle = gw.rows[0].internal_title;
    const publishLabel  = publish_type === 'immediate'
      ? 'сразу после утверждения'
      : `в ${new Date(scheduled_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} (МСК)`;

    const botToken = process.env.BOT_TOKEN;
    const invoiceResp = await fetch(
      `https://api.telegram.org/bot${botToken}/createInvoiceLink`,
      {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title:          'Продвижение в боте',
          description:    `«${giveawayTitle}» — публикация ${publishLabel}`,
          payload:        JSON.stringify({
            type:         'bot_promotion',
            giveaway_id:  Number(giveaway_id),
            publish_type,
            scheduled_at: scheduled_at || null,
            user_id:      userId,
          }),
          currency:       'XTR',
          prices:         [{ label: 'Продвижение в боте', amount: PROMOTION_PRICE_STARS }],
          provider_token: '',
        }),
      }
    );

    const invoiceData = await invoiceResp.json();
    if (!invoiceData.ok) {
      console.error('[API create_promotion_stars_invoice] Telegram error:', invoiceData);
      return res.status(500).json({ ok: false, reason: 'telegram_api_error' });
    }

    return res.json({ ok: true, invoice_link: invoiceData.result });

  } catch (error) {
    console.error('[API create_promotion_stars_invoice] error:', error);
    return res.status(500).json({ ok: false, reason: 'server_error: ' + error.message });
  }
});

// --- POST /api/promotion_after_payment ---
// Вызывается ботом после успешной оплаты Stars (pre_checkout → successful_payment)
// Создаёт запись в bot_promotions
app.post('/api/promotion_after_payment', async (req, res) => {
  try {
    const { giveaway_id, user_id, publish_type, scheduled_at, price_stars } = req.body;

    await pool.query(`
      INSERT INTO bot_promotions
        (giveaway_id, owner_user_id, status, payment_method, payment_status,
         price_stars, publish_type, scheduled_at)
      VALUES ($1, $2, 'pending', 'stars', 'paid', $3, $4, $5)
      ON CONFLICT DO NOTHING
    `, [
      Number(giveaway_id),
      Number(user_id),
      Number(price_stars) || PROMOTION_PRICE_STARS,
      publish_type || 'immediate',
      scheduled_at ? new Date(scheduled_at) : null,
    ]);

    return res.json({ ok: true });
  } catch (error) {
    console.error('[API promotion_after_payment] error:', error);
    return res.status(500).json({ ok: false, reason: 'server_error: ' + error.message });
  }
});


// --- POST /api/participant_giveaways ---
// Отдает список розыгрышей участника по вкладке (active/finished/cancelled)
app.post('/api/participant_giveaways', async (req, res) => {
  try {
    const { init_data, status } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    if (!Number.isFinite(userId)) {
      return res.status(400).json({ ok: false, reason: 'bad_user_id' });
    }

    // status bucket (строго под UI-вкладки)
    let whereStatusSql = '';
    if (status === 'active') {
      whereStatusSql = `AND g.status = 'active'`;
    } else if (status === 'finished') {
      whereStatusSql = `AND g.status IN ('finished','completed')`;
    } else if (status === 'cancelled') {
      whereStatusSql = `AND g.status = 'cancelled'`;
    } else {
      return res.status(400).json({ ok: false, reason: 'bad_status' });
    }

    const result = await pool.query(`
      SELECT
        g.id,
        g.internal_title,
        g.end_at_utc,
        g.status,

        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,

        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id

      FROM entries e
      JOIN giveaways g ON g.id = e.giveaway_id
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id

      WHERE e.user_id = $1
        AND e.prelim_ok = true
      ${whereStatusSql}

      GROUP BY g.id
      ORDER BY g.id DESC
    `, [userId]);

    const rows = result.rows || [];

    const items = rows.map(row => {
      const firstChatId = row.first_channel_chat_id || null;
      return {
        id: row.id,
        title: row.internal_title,
        end_at_utc: row.end_at_utc,
        status: row.status,
        channels: row.channels || [],
        first_channel_avatar_url: firstChatId ? `/api/chat_avatar/${firstChatId}` : null,
      };
    });

    return res.json({ ok: true, total: items.length, items });

  } catch (error) {
    console.error('[API participant_giveaways] error:', error);
    return res.status(500).json({
      ok: false,
      reason: 'server_error',
      error: error.message
    });
  }
});


// --- POST /api/creator_giveaway_details ---
// Детали розыгрыша для страницы "проваливания" (creator)
app.post('/api/creator_giveaway_details', async (req, res) => {
  try {
    const { init_data, giveaway_id } = req.body;

    const parsedInitData = _tgCheckMiniAppInitData(init_data);
    if (!parsedInitData || !parsedInitData.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsedInitData.user_parsed.id);
    const gid = Number(giveaway_id);

    if (!Number.isFinite(userId) || !Number.isFinite(gid)) {
      return res.status(400).json({ ok: false, reason: 'bad_params' });
    }

    // 1) розыгрыш (проверяем владельца)
    const gRes = await pool.query(`
      SELECT
        id,
        owner_user_id,
        internal_title,
        public_description,
        photo_file_id,
        end_at_utc,
        status,
        media_position
      FROM giveaways
      WHERE id = $1 AND owner_user_id = $2
      LIMIT 1
    `, [gid, userId]);

    if (!gRes.rows?.length) {
      return res.status(404).json({ ok: false, reason: 'not_found' });
    }

    const g = gRes.rows[0];

    // 2) каналы/группы розыгрыша
    // В твоей схеме giveaway_channels уже используется вместе с organizer_channels (как в /api/creator_giveaways)
    const cRes = await pool.query(`
      SELECT
        gc.chat_id,
        COALESCE(gc.title, oc.title, oc.username) AS title
      FROM giveaway_channels gc
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE gc.giveaway_id = $1
      ORDER BY gc.id ASC
    `, [gid]);

    const channels = (cRes.rows || []).map(r => ({
      chat_id: r.chat_id,
      title: r.title,
      avatar_url: r.chat_id ? `/api/chat_avatar/${r.chat_id}` : null
    }));

    // 3) media: отдаем URL на наш прокси-роут
    const hasPhoto = !!g.photo_file_id;

    return res.json({
      ok: true,
      id: g.id,
      title: g.internal_title,
      description: g.public_description,
      end_at_utc: g.end_at_utc,
      status: g.status,
      media_position: g.media_position,

      media: {
        url: hasPhoto ? `/api/giveaway_media/${g.id}` : null,
        type: hasPhoto ? 'image' : null
      },

      channels
    });

  } catch (error) {
    console.error('[API creator_giveaway_details] error:', error);
    return res.status(500).json({
      ok: false,
      reason: 'server_error',
      error: error.message
    });
  }
});

// POST /api/participant_giveaway_details
app.post('/api/participant_giveaway_details', async (req, res) => {
  try {
    const { init_data, giveaway_id } = req.body || {};

    // 1) Валидация init_data (используем твой уже существующий парсер/проверку)
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed || !parsed.user_parsed) {
      return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    }

    const userId = Number(parsed.user_parsed.id);
    const gid = Number(giveaway_id);

    if (!Number.isFinite(userId) || !Number.isFinite(gid)) {
      return res.status(400).json({ ok: false, reason: 'bad_params' });
    }

    // 2) Берём данные розыгрыша + первый канал + message_id (как в bot.py)
    const q = await pool.query(
      `
      SELECT
        g.id,
        g.internal_title,
        g.public_description,
        g.end_at_utc,
        g.photo_file_id,
        g.media_position,

        oc.chat_id,
        oc.username,
        gc.message_id

      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id

      WHERE g.id = $1
      ORDER BY gc.id ASC
      LIMIT 1
      `,
      [gid]
    );

    if (!q.rows || q.rows.length === 0) {
      return res.status(404).json({ ok: false, reason: 'not_found' });
    }

    const row = q.rows[0];

    const hasPhoto = !!row.photo_file_id;

    // 3) Билеты участника (в твоей системе билет = entry.ticket_code)
    const t = await pool.query(
      `
      SELECT ticket_code
      FROM entries
      WHERE giveaway_id = $1 AND user_id = $2
      ORDER BY id ASC
      `,
      [gid, userId]
    );

    const tickets = (t.rows || []).map(r => r.ticket_code).filter(Boolean);

    // 4) Ссылки на пост (1:1 логике bot.py)
    let post_url = null;
    const username = row.username ? String(row.username).replace(/^@/, '') : null;
    const message_id = row.message_id ? Number(row.message_id) : null;
    const chat_id = row.chat_id ? Number(row.chat_id) : null;

    if (message_id) {
      if (username) {
        post_url = `https://t.me/${username}/${message_id}`;
      } else if (chat_id) {
        // _tg_internal_chat_id аналог твоего bot.py: t.me/c/<internal>/<message_id>
        // internal = abs(chat_id) - 1000000000000 для супергрупп/каналов
        const absId = Math.abs(chat_id);
        const internal = absId > 1000000000000 ? (absId - 1000000000000) : null;
        if (internal) post_url = `https://t.me/c/${internal}/${message_id}`;
      }
    }

    // 5) Каналы/группы (нужно для блока “Подключенные каналы / группы”)
    const c = await pool.query(
      `
      SELECT
        oc.chat_id,
        oc.username,
        COALESCE(oc.title, oc.username) AS title,
        gc.message_id
      FROM giveaway_channels gc
      JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE gc.giveaway_id = $1
      ORDER BY gc.id ASC
      `,
      [gid]
    );

    const channels = (c.rows || []).map(r => {
      const uname = r.username ? String(r.username).replace(/^@/, '') : null;
      const mid = r.message_id ? Number(r.message_id) : null;
      let url = null;

      if (mid) {
        if (uname) {
          url = `https://t.me/${uname}/${mid}`;
        } else {
          const absId = Math.abs(Number(r.chat_id));
          const internal = absId > 1000000000000 ? (absId - 1000000000000) : null;
          if (internal) url = `https://t.me/c/${internal}/${mid}`;
        }
      }

      return {
        chat_id: r.chat_id,
        title: r.title,
        username: uname,
        post_url: url,
        avatar_url: r.chat_id ? `/api/chat_avatar/${r.chat_id}` : null,
      };
    });

    // 6) Ответ
    return res.json({
      ok: true,
      id: row.id,
      title: row.internal_title,
      description: row.public_description,
      end_at_utc: row.end_at_utc,
      tickets,
      post_url,
      channels,
      media_position: row.media_position,
      media: {
        url: hasPhoto ? `/api/giveaway_media/${row.id}` : null,
        type: hasPhoto ? 'image' : null
      },
    });

  } catch (e) {
    console.error('[participant_giveaway_details]', e);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});


// --- POST /api/verify_captcha ---
app.post('/api/verify_captcha', async (req, res) => {
  console.log('[SIMPLE-CAPTCHA] Verify request received');
  
  try {
    const { token, giveaway_id, user_id, answer } = req.body;  // Добавлен answer
    
    if (!token || !giveaway_id || !user_id || !answer) {
      return res.status(400).json({ 
        ok: false, 
        error: 'missing_parameters',
        message: 'Отсутствуют обязательные параметры' 
      });
    }
    
    console.log(`[SIMPLE-CAPTCHA] For giveaway ${giveaway_id}, user ${user_id}, answer: ${answer}`);
    
    // 🔄 ИНТЕГРАЦИЯ С PYTHON БОТОМ - НОВЫЙ ENDPOINT
    try {
      const botApiResponse = await fetch('http://127.0.0.1:8088/api/verify_simple_captcha_and_participate', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          user_id: parseInt(user_id),
          giveaway_id: parseInt(giveaway_id),
          captcha_answer: answer,      // Введенные пользователем цифры
          captcha_token: token         // Токен для проверки
        }),
        timeout: 10000
      });
      
      console.log(`[SIMPLE-CAPTCHA] Bot API response status: ${botApiResponse.status}`);
      
      if (!botApiResponse.ok) {
        console.error(`[SIMPLE-CAPTCHA] Bot API error: ${botApiResponse.status}`);
        throw new Error(`Bot API error: ${botApiResponse.status}`);
      }
      
      const botApiData = await botApiResponse.json();
      console.log(`[SIMPLE-CAPTCHA] Bot API data:`, JSON.stringify(botApiData));
      
      // Возвращаем результат от бота
      return res.json(botApiData);
      
    } catch (botError) {
      console.error('[SIMPLE-CAPTCHA] Bot API connection error:', botError);
      
      // Fallback для тестового режима
      if (process.env.CAPTCHA_ENABLED !== 'true') {
        console.log('[SIMPLE-CAPTCHA] Using test mode due to bot connection error');
        // Простая проверка для тестового режима
        const isValid = token.startsWith('test_token_') && answer === '1234';
        return res.json({ 
          ok: isValid, 
          message: isValid ? '✅ Проверка пройдена (тестовый режим)' : '❌ Неверные цифры',
          ticket_code: isValid ? 'TEST123' : null,
          already_participating: false
        });
      }
      
      throw botError;
    }
    
  } catch (error) {
    console.error('[SIMPLE-CAPTCHA] Error:', error);
    return res.status(500).json({ 
      ok: false, 
      error: 'server_error',
      message: 'Ошибка проверки. Попробуйте позже.'
    });
  }
});

app.post("/api/create_captcha_session", async (req, res) => {
  try {
    const giveaway_id = parseInt(req.body?.giveaway_id, 10);
    const user_id = parseInt(req.body?.user_id, 10);

    if (!giveaway_id || !user_id) {
      return res.status(400).json({ ok: false, error: "missing_parameters", message: "giveaway_id и user_id обязательны" });
    }

    const botUrl = (process.env.BOT_INTERNAL_URL || "http://127.0.0.1:8088") + "/api/create_simple_captcha_session";

    const r = await fetch(botUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ giveaway_id, user_id }),
    });

    const data = await r.json().catch(() => ({}));
    return res.status(r.status).json(data);

  } catch (e) {
    console.error("[API] /api/create_captcha_session error:", e);
    return res.status(500).json({ ok: false, error: "server_error" });
  }
});

// GET /api/captcha_config
app.get('/api/captcha_config', (req, res) => {
  res.json({
    site_key: process.env.CAPTCHA_SITE_KEY || '0x4AAAAAACLE0aRcmDlHJuzo',
    test_mode: process.env.NODE_ENV !== 'production',
    enabled: process.env.CAPTCHA_ENABLED === 'true'
  });
});

// Check if giveaway requires captcha
app.post('/api/requires_captcha', async (req, res) => {
  try {
    console.log('[CAPTCHA] Checking requirement for giveaway:', req.body);
    
    const { giveaway_id } = req.body;
    
    if (!giveaway_id) {
      return res.status(400).json({ error: 'giveaway_id is required' });
    }
    
    // Проверяем в БД, активна ли механика Captcha для этого розыгрыша
    const result = await pool.query(
      `SELECT is_active FROM giveaway_mechanics 
       WHERE giveaway_id = $1 AND mechanic_type = 'captcha'`,
      [giveaway_id]
    );
    
    const requires_captcha = result.rows.length > 0 && result.rows[0].is_active === true;
    
    console.log('[CAPTCHA] Result:', { giveaway_id, requires_captcha });
    
    res.json({ requires_captcha });
    
  } catch (error) {
    console.error('[CAPTCHA] Error checking requirement:', error);
    res.status(500).json({ error: 'server_error' });
  }
});

// Captcha page route
app.get('/miniapp/captcha', (req, res) => {
    res.sendFile(path.join(__dirname, '../webapp/captcha.html'));
});

// ── GET /api/creator_channels — каналы/группы пользователя ──────────────────
app.post('/api/creator_channels', async (req, res) => {
  try {
    const { init_data } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(401).json({ ok: false, reason: 'unauthorized' });

    const userId = parsed.user_parsed.id;

    const result = await pool.query(
      `SELECT
         oc.id,
         oc.chat_id,
         oc.username,
         oc.title,
         oc.is_private,
         oc.member_count,
         oc.channel_type
       FROM organizer_channels oc
       WHERE oc.owner_user_id = $1
       ORDER BY oc.id ASC`,
      [userId]
    );

    const channels = result.rows.map(r => ({
      id: r.id,
      chat_id: String(r.chat_id),
      username: r.username || null,
      title: r.title,
      member_count: r.member_count !== null ? Number(r.member_count) : null,
      channel_type: r.channel_type || 'channel',
      avatar_url: r.chat_id ? `/api/chat_avatar/${r.chat_id}` : null,
    }));

    return res.json({ ok: true, channels });
  } catch (e) {
    console.error('[creator_channels] error:', e);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ── POST /api/creator_channel_refresh — обновить число подписчиков ─────────
app.post('/api/creator_channel_refresh', async (req, res) => {
  try {
    const { init_data, channel_id } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(401).json({ ok: false, reason: 'unauthorized' });

    const userId = parsed.user_parsed.id;
    const channelId = parseInt(channel_id, 10);
    if (!channelId) return res.status(400).json({ ok: false, reason: 'bad_channel_id' });

    const ownerCheck = await pool.query(
      'SELECT id, chat_id FROM organizer_channels WHERE id = $1 AND owner_user_id = $2',
      [channelId, userId]
    );
    if (!ownerCheck.rows.length) return res.status(403).json({ ok: false, reason: 'forbidden' });

    const chatId = ownerCheck.rows[0].chat_id;

    // Получаем число участников и тип чата через Telegram API
    let memberCount = null;
    let channelType = 'channel';
    try {
      const [countResp, chatResp] = await Promise.all([
        fetch(`${TELEGRAM_API}/getChatMemberCount?chat_id=${chatId}`),
        fetch(`${TELEGRAM_API}/getChat?chat_id=${chatId}`)
      ]);
      const countData = await countResp.json();
      const chatData = await chatResp.json();

      if (countData.ok) memberCount = countData.result;
      if (chatData.ok) {
        const t = chatData.result.type;
        channelType = (t === 'group' || t === 'supergroup') ? 'group' : 'channel';
      }
    } catch (e) {
      console.warn('[creator_channel_refresh] Telegram API error:', e.message);
    }

    await pool.query(
      'UPDATE organizer_channels SET member_count = COALESCE($1, member_count), channel_type = $2 WHERE id = $3',
      [memberCount, channelType, channelId]
    );

    return res.json({ ok: true, member_count: memberCount, channel_type: channelType });
  } catch (e) {
    console.error('[creator_channel_refresh] error:', e);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ── POST /api/creator_channel_delete — удалить канал ────────────────────────
app.post('/api/creator_channel_delete', async (req, res) => {
  try {
    const { init_data, channel_id } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(401).json({ ok: false, reason: 'unauthorized' });

    const userId = parsed.user_parsed.id;
    const channelId = parseInt(channel_id, 10);
    if (!channelId) return res.status(400).json({ ok: false, reason: 'bad_channel_id' });

    // Проверяем владельца
    const ownerCheck = await pool.query(
      'SELECT id FROM organizer_channels WHERE id = $1 AND owner_user_id = $2',
      [channelId, userId]
    );
    if (!ownerCheck.rows.length) return res.status(403).json({ ok: false, reason: 'forbidden' });

    // Удаляем (каскад в giveaway_channels настроен на уровне БД)
    await pool.query('DELETE FROM organizer_channels WHERE id = $1', [channelId]);

    return res.json({ ok: true });
  } catch (e) {
    console.error('[creator_channel_delete] error:', e);
    return res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ══════════════════════════════════════════════════════════════════════════
// ── СТАТИСТИКА СОЗДАТЕЛЯ ──────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════

// ── /api/stats/overview — общий дашборд создателя ────────────────────────
app.post('/api/stats/overview', async (req, res) => {
  try {
    const { init_data } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    const userId = parsed.user_parsed.id;

    const result = await pool.query(`
      SELECT
        COUNT(DISTINCT g.id)                                            AS total_giveaways,
        COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'active')        AS active_giveaways,
        COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'finished')      AS finished_giveaways,
        COUNT(DISTINCT e.user_id)                                       AS total_unique_participants,
        COUNT(e.id)                                                     AS total_entries,
        COALESCE(SUM(CASE WHEN so.service_type = 'top_placement'   THEN COALESCE(so.price_rub,0) ELSE 0 END), 0) AS spent_top_rub,
        COALESCE(SUM(CASE WHEN so.service_type = 'bot_promotion'   THEN COALESCE(bp.price_stars,0) ELSE 0 END), 0) AS spent_promo_stars
      FROM giveaways g
      LEFT JOIN entries e        ON e.giveaway_id = g.id AND e.prelim_ok = true
      LEFT JOIN service_orders so ON so.giveaway_id = g.id AND so.owner_user_id = $1
      LEFT JOIN bot_promotions bp ON bp.giveaway_id = g.id AND bp.owner_user_id = $1
      WHERE g.owner_user_id = $1
    `, [userId]);

    // Топ розыгрышей по участникам
    const topResult = await pool.query(`
      SELECT g.id, g.internal_title, g.status, g.created_at, g.end_at_utc,
             COUNT(e.id) FILTER (WHERE e.prelim_ok = true) AS participants
      FROM giveaways g
      LEFT JOIN entries e ON e.giveaway_id = g.id
      WHERE g.owner_user_id = $1
      GROUP BY g.id
      ORDER BY participants DESC
      LIMIT 5
    `, [userId]);

    // Динамика по дням (последние 30 дней)
    const trendsResult = await pool.query(`
      SELECT
        date_trunc('day', e.created_at) AS day,
        COUNT(e.id) AS new_entries
      FROM entries e
      JOIN giveaways g ON g.id = e.giveaway_id
      WHERE g.owner_user_id = $1
        AND e.prelim_ok = true
        AND e.created_at >= NOW() - INTERVAL '30 days'
      GROUP BY day
      ORDER BY day ASC
    `, [userId]);

    res.json({
      ok: true,
      overview: result.rows[0],
      top_giveaways: topResult.rows,
      trends: trendsResult.rows
    });
  } catch (e) {
    console.error('[stats/overview]', e);
    res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ── /api/stats/giveaway — детальная статистика розыгрыша ─────────────────
app.post('/api/stats/giveaway', async (req, res) => {
  try {
    const { init_data, giveaway_id } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    const userId = parsed.user_parsed.id;
    const gid = parseInt(giveaway_id);

    // Проверяем что розыгрыш принадлежит этому пользователю
    const ownerCheck = await pool.query(
      'SELECT id, internal_title, status, created_at, end_at_utc FROM giveaways WHERE id = $1 AND owner_user_id = $2',
      [gid, userId]
    );
    if (!ownerCheck.rows.length) return res.status(403).json({ ok: false, reason: 'not_found' });
    const giveaway = ownerCheck.rows[0];

    // Базовые метрики
    const metricsResult = await pool.query(`
      SELECT
        (SELECT COUNT(*) FROM giveaway_clicks WHERE giveaway_id = $1)   AS total_clicks,
        COUNT(DISTINCT e.user_id) FILTER (WHERE e.prelim_ok = true)     AS participants,
        COUNT(DISTINCT e.user_id) FILTER (WHERE e.prelim_ok = false)    AS dropped
      FROM entries e WHERE e.giveaway_id = $1
    `, [gid]);

    // Динамика по часам (последние 7 дней) или по дням (всё время)
    const hourlyResult = await pool.query(`
      SELECT
        date_trunc('hour', created_at) AS bucket,
        COUNT(*) FILTER (WHERE prelim_ok = true) AS participants
      FROM entries
      WHERE giveaway_id = $1
      GROUP BY bucket ORDER BY bucket ASC
    `, [gid]);

    const dailyResult = await pool.query(`
      SELECT
        date_trunc('day', created_at) AS bucket,
        COUNT(*) FILTER (WHERE prelim_ok = true) AS participants
      FROM entries
      WHERE giveaway_id = $1
      GROUP BY bucket ORDER BY bucket ASC
    `, [gid]);

    // Источники по каналам
    const sourcesResult = await pool.query(`
      SELECT
        oc.id AS channel_id,
        oc.title,
        oc.username,
        oc.chat_id,
        COUNT(e.id) FILTER (WHERE e.prelim_ok = true) AS participants
      FROM giveaway_channels gc
      JOIN organizer_channels oc ON oc.id = gc.channel_id
      LEFT JOIN entries e ON e.giveaway_id = gc.giveaway_id
        AND e.source_channel_id = oc.chat_id
      WHERE gc.giveaway_id = $1
      GROUP BY oc.id, oc.title, oc.username, oc.chat_id
      ORDER BY participants DESC
    `, [gid]);

    // Новые подписчики по каналам (was_subscribed = false → стали участником)
    const newSubsResult = await pool.query(`
      SELECT
        es.channel_id,
        es.channel_id AS chat_id,
        oc.title,
        oc.username,
        COUNT(DISTINCT es.user_id) AS new_subscribers
      FROM entry_subscriptions es
      LEFT JOIN organizer_channels oc ON oc.chat_id = es.channel_id
      WHERE es.giveaway_id = $1 AND es.was_subscribed = false
      GROUP BY es.channel_id, oc.title, oc.username
      ORDER BY new_subscribers DESC
    `, [gid]);

    // Список пользователей-новых подписчиков с именами
    const newSubUsersResult = await pool.query(`
      SELECT DISTINCT ON (es.user_id, es.channel_id)
        es.user_id,
        es.channel_id,
        u.username,
        u.first_name,
        u.photo_url
      FROM entry_subscriptions es
      JOIN users u ON u.user_id = es.user_id
      WHERE es.giveaway_id = $1 AND es.was_subscribed = false
      ORDER BY es.user_id, es.channel_id
      LIMIT 100
    `, [gid]);

    // Аудитория: Premium vs обычные
    const premiumResult = await pool.query(`
      SELECT
        COUNT(*) FILTER (WHERE u.is_premium = true)  AS premium_count,
        COUNT(*) FILTER (WHERE u.is_premium = false) AS regular_count
      FROM entries e
      JOIN users u ON u.user_id = e.user_id
      WHERE e.giveaway_id = $1 AND e.prelim_ok = true
    `, [gid]);

    // Языки (как прокси для географии)
    const languagesResult = await pool.query(`
      SELECT
        COALESCE(u.language_code, 'unknown') AS lang,
        COUNT(*) AS cnt
      FROM entries e
      JOIN users u ON u.user_id = e.user_id
      WHERE e.giveaway_id = $1 AND e.prelim_ok = true
      GROUP BY lang ORDER BY cnt DESC LIMIT 10
    `, [gid]);

    // Воронка: уникальные клики → получили билет
    const funnelResult = await pool.query(`
      SELECT
        (SELECT COUNT(*) FROM giveaway_clicks WHERE giveaway_id = $1)        AS total_clicks,
        COUNT(DISTINCT user_id) FILTER (WHERE prelim_ok = true)              AS got_ticket
      FROM entries WHERE giveaway_id = $1
    `, [gid]);

    // Финансы по этому розыгрышу
    const financeResult = await pool.query(`
      SELECT
        COALESCE(SUM(so.price_rub), 0) AS total_rub,
        service_type,
        COUNT(*) AS orders_count
      FROM service_orders so
      WHERE so.giveaway_id = $1 AND so.status IN ('paid', 'active')
      GROUP BY service_type
    `, [gid]);

    const promoFinanceResult = await pool.query(`
      SELECT COALESCE(SUM(price_stars), 0) AS total_stars, COUNT(*) AS orders_count
      FROM bot_promotions
      WHERE giveaway_id = $1 AND payment_status = 'paid'
    `, [gid]);

    // Победители (если завершён)
    const winnersResult = await pool.query(`
      SELECT w.rank, w.user_id, u.username, u.first_name, e.ticket_code
      FROM winners w
      LEFT JOIN users u ON u.user_id = w.user_id
      LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
      WHERE w.giveaway_id = $1
      ORDER BY w.rank ASC
    `, [gid]);

    res.json({
      ok: true,
      giveaway,
      metrics:      metricsResult.rows[0],
      hourly:       hourlyResult.rows,
      daily:        dailyResult.rows,
      sources:      sourcesResult.rows,
      new_subs:     newSubsResult.rows,
      new_sub_users: newSubUsersResult.rows,
      premium:      premiumResult.rows[0],
      languages:    languagesResult.rows,
      funnel:       funnelResult.rows[0],
      finance:      financeResult.rows,
      promo_finance: promoFinanceResult.rows[0],
      winners:      winnersResult.rows,
    });
  } catch (e) {
    console.error('[stats/giveaway]', e);
    res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ── /api/stats/giveaways_list — список розыгрышей для выбора ─────────────
app.post('/api/stats/giveaways_list', async (req, res) => {
  try {
    const { init_data } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    const userId = parsed.user_parsed.id;

    const result = await pool.query(`
      SELECT
        g.id, g.internal_title, g.status, g.created_at, g.end_at_utc,
        COUNT(DISTINCT e.user_id) FILTER (WHERE e.prelim_ok = true) AS participants,
        array_agg(DISTINCT COALESCE(oc.title, oc.username)) FILTER (WHERE oc.id IS NOT NULL) AS channels,
        MIN(oc.username) AS first_channel_username,
        (array_agg(oc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id
      FROM giveaways g
      LEFT JOIN entries e ON e.giveaway_id = g.id
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
      WHERE g.owner_user_id = $1
      GROUP BY g.id
      ORDER BY g.created_at DESC
    `, [userId]);

    res.json({ ok: true, items: result.rows });
  } catch (e) {
    console.error('[stats/giveaways_list]', e);
    res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// ── /api/stats/request_csv — отправить пользователю кнопку CSV через бота ──
app.post('/api/stats/request_csv', async (req, res) => {
  try {
    const { init_data, giveaway_id } = req.body;
    const parsed = _tgCheckMiniAppInitData(init_data);
    if (!parsed) return res.status(400).json({ ok: false, reason: 'bad_initdata' });
    const userId = parsed.user_parsed.id;
    const gid    = parseInt(giveaway_id);

    // Проверяем принадлежность розыгрыша
    const ownerCheck = await pool.query(
      'SELECT id, internal_title FROM giveaways WHERE id = $1 AND owner_user_id = $2',
      [gid, userId]
    );
    if (!ownerCheck.rows.length) return res.status(403).json({ ok: false, reason: 'not_found' });

    // Дёргаем внутренний HTTP endpoint бота для генерации и отправки CSV
    const botRes = await fetch(`${BOT_INTERNAL_URL}/internal/csv_export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, giveaway_id: gid })
    });

    const botData = await botRes.json();
    if (!botData.ok) throw new Error(botData.reason || 'bot_error');

    res.json({ ok: true, bot_username: botData.bot_username });
  } catch (e) {
    console.error('[stats/request_csv]', e);
    res.status(500).json({ ok: false, reason: 'server_error' });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`🎯 PrizeMe Node.js backend running on port ${PORT}`);
  console.log(`📊 Using existing .env configuration`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
});
