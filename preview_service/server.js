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
app.use('/miniapp', express.static(path.join(__dirname, '../webapp')));


// Конфигурация из .env
const BOT_TOKEN = process.env.BOT_TOKEN?.trim();
const BOT_INTERNAL_URL = process.env.BOT_INTERNAL_URL || 'http://127.0.0.1:8088';
const WEBAPP_BASE_URL = process.env.WEBAPP_BASE_URL?.trim();
const TELEGRAM_API = BOT_TOKEN ? `https://api.telegram.org/bot${BOT_TOKEN}` : null;

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

// Serve static files from webapp directory
app.use('/miniapp-static', express.static(path.join(__dirname, '../webapp')));

// HTML endpoints for Mini App
app.get('/miniapp/', (req, res) => {
  const tgWebAppStartParam = req.query.tgWebAppStartParam;
  console.log('🎯 [ROOT] Request to /miniapp/, tgWebAppStartParam:', tgWebAppStartParam);
  
  if (tgWebAppStartParam && tgWebAppStartParam !== 'demo') {
    console.log('🎯 [ROOT] Serving loading page with gid:', tgWebAppStartParam);
    
    // Отправляем HTML который сохранит параметр и init_data и сразу перейдет на loading
    res.send(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>PrizeMe - Loading</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script>
          (function() {
            try {
              var tg = window.Telegram && Telegram.WebApp;
              if (tg && tg.initData) {
                sessionStorage.setItem('prizeme_init_data', tg.initData);
                console.log('🎯 [ROOT-SCRIPT] Saved init_data to sessionStorage, length:', tg.initData.length);
              } else {
                console.log('⚠️ [ROOT-SCRIPT] Telegram WebApp or initData not available on root page');
              }
            } catch (e) {
              console.log('❌ [ROOT-SCRIPT] Error while reading initData:', e);
            }

            // Сохраняем gid
            sessionStorage.setItem('prizeme_gid', '${tgWebAppStartParam}');
            console.log('🎯 [ROOT-SCRIPT] Saved gid to sessionStorage:', '${tgWebAppStartParam}');
            
            // Немедленный переход на loading
            window.location.href = '/miniapp/loading?gid=${tgWebAppStartParam}';
          })();
        </script>
      </head>
      <body>
        <p>Redirecting to participation...</p>
      </body>
      </html>
    `);
  } else {
    console.log('❌ [ROOT] No valid start param, redirecting to index');
    res.redirect('/miniapp/index');
  }
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

    const userId = parseInt(parsedInitData.user_parsed.id);
    console.log(`[CHECK] user_id=${userId}, gid=${giveawayId}`);

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

    console.log(`[CHECK] channels_from_db:`, channels);

    if (!channels.length) {
      return res.json({
        ok: true,
        done: false,
        need: [{ title: "Ошибка конфигурации", username: null, url: "#" }],
        details: ["No channels configured for this giveaway"],
        end_at_utc: endAtUtc
      });
    }

    // Проверка подписки на каналы
    const need = [];
    const details = [];
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

    console.log(`[CHECK] user_id=${userId}, is_ok_overall=${isOkOverall}`);
    console.log(`[CHECK] need list:`, need);

    const done = isOkOverall;
    let ticket = null;
    let isNewTicket = false;

    // Если все условия выполнены - создаем/проверяем билет
    if (done) {
      try {
        // Ищем существующий билет
        const ticketResult = await pool.query(
          'SELECT ticket_code FROM entries WHERE giveaway_id = $1 AND user_id = $2',
          [giveawayId, userId]
        );

        if (ticketResult.rows.length > 0) {
          ticket = ticketResult.rows[0].ticket_code;
          console.log(`[CHECK] ✅ Найден существующий билет: ${ticket}`);
        } else {
          console.log(`[CHECK] 📝 Создаем новый билет для user_id=${userId}, gid=${giveawayId}`);
          
          // Генерация уникального кода билета
          const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
          for (let attempt = 0; attempt < 8; attempt++) {
            const code = Array.from({ length: 6 }, () => 
              alphabet[Math.floor(Math.random() * alphabet.length)]
            ).join('');
            
            try {
              await pool.query(
                `INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) 
                 VALUES ($1, $2, $3, true, NOW())`,
                [giveawayId, userId, code]
              );
              ticket = code;
              isNewTicket = true;
              console.log(`[CHECK] ✅ Создан новый билет: ${ticket} (попытка ${attempt + 1})`);
              break;
            } catch (error) {
              if (error.code === '23505') { // UNIQUE constraint violation
                console.log(`[CHECK] ⚠️ Коллизия билета ${code}, пробуем другой`);
                continue;
              } else {
                throw error;
              }
            }
          }
        }
      } catch (error) {
        console.log(`[CHECK] ❌ Ошибка при работе с билетом: ${error}`);
        details.push(`ticket_issue_error: ${error.message}`);
      }
    }

    // Финальный ответ
    res.json({
      ok: true,
      done: done,
      need: need,
      ticket: ticket,
      is_new_ticket: isNewTicket,
      end_at_utc: endAtUtc,
      details: details,
      channels: channels 
    });

  } catch (error) {
    console.log(`[CHECK] Error: ${error}`);
    res.status(500).json({ ok: false, reason: `server_error: ${error.message}` });
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
        await pool.query(
          `INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) 
           VALUES ($1, $2, $3, true, NOW())`,
          [giveawayId, userId, code]
        );
        ticket = code;
        console.log(`[CLAIM] ✅ Успешно создан билет: ${code}`);
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

// --- POST /api/participant_home_giveaways ---
// Отдает списки розыгрышей для главной страницы участника:
// top — "Топ розыгрыши", latest — "Все текущие розыгрыши"
// Пока логика одинаковая: последние активные розыгрыши.
app.post('/api/participant_home_giveaways', async (req, res) => {
  try {
    const limitTop = 5;
    const limitLatest = 5;
    const limit = Math.max(limitTop, limitLatest);

    const result = await pool.query(`
      SELECT
        g.id,
        g.internal_title,
        g.public_description,
        g.end_at_utc,
        g.status,

        -- список названий каналов как раньше
        array_remove(
          array_agg(DISTINCT COALESCE(gc.title, oc.title, oc.username)),
          NULL
        ) AS channels,

        -- первый канал по gc.id (важно: именно порядок привязки)
        (array_agg(gc.chat_id ORDER BY gc.id))[1] AS first_channel_chat_id,

        -- количество участников (как минимум уникальные user_id с final_ok=true)
        (
          SELECT COUNT(DISTINCT e.user_id)
          FROM entries e
          WHERE e.giveaway_id = g.id
        ) AS participants_count

      FROM giveaways g
      LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
      LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id

      WHERE g.status = 'active'
      GROUP BY g.id
      ORDER BY g.id DESC
      LIMIT $1
    `, [limit]);

    const rows = result.rows || [];

    const mapped = rows.map(row => {
      const firstChatId = row.first_channel_chat_id || null;
      return {
        id: row.id,
        title: row.internal_title,
        public_description: row.public_description,
        end_at_utc: row.end_at_utc,
        status: row.status,
        channels: row.channels || [],

        // фронту даем URL на наш прокси-роут
        first_channel_avatar_url: firstChatId ? `/api/chat_avatar/${firstChatId}` : null,

        participants_count: typeof row.participants_count === 'number'
          ? row.participants_count
          : (row.participants_count ? Number(row.participants_count) : 0),
      };
    });

    res.json({
      ok: true,
      top: mapped.slice(0, limitTop),
      latest: mapped.slice(0, limitLatest),
    });

  } catch (error) {
    console.log('[API participant_home_giveaways] error:', error);
    res.status(500).json({
      ok: false,
      reason: 'server_error: ' + error.message
    });
  }
});


// --- GET /api/chat_avatar/:chatId ---
// Отдает ПРЯМУЮ ссылку на файл аватара Telegram-канала
app.get('/api/chat_avatar/:chatId', async (req, res) => {
    try {
        const { chatId } = req.params;
        console.log(`[API chat_avatar] Request for chat_id: ${chatId}`);

        const telegramChatId = parseInt(chatId);
        if (!telegramChatId || !BOT_TOKEN) {
            // Если что-то не так, возвращаем заглушку через наш прокси
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
        // В случае ошибки тоже показываем заглушку
        res.redirect('/uploads/avatars/default_channel.png');
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

// Start server
app.listen(PORT, () => {
  console.log(`🎯 PrizeMe Node.js backend running on port ${PORT}`);
  console.log(`📊 Using existing .env configuration`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
});
