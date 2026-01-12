// MULTI-PAGE-V1 — многостраничная версия Mini App
console.log("[PrizeMe][MULTI-PAGE-V1] app.js start");

const tg = window.Telegram?.WebApp || {};
tg.expand?.();
tg.enableClosingConfirmation?.(false);

const $ = (q) => document.querySelector(q);
const show = (sel) => $(sel)?.classList.remove("hide");
const hide = (sel) => $(sel)?.classList.add("hide");

// Инициализация Telegram WebApp
function initializeTelegramWebApp() {
  const tg = window.Telegram?.WebApp;
  if (!tg) {
    console.error('❌ Telegram WebApp is not available');
    return false;
  }

  console.log('✅ Telegram WebApp initialized');
  console.log('📱 Platform:', tg.platform);
  console.log('🔢 Version:', tg.version);
  console.log('👤 User:', tg.initDataUnsafe?.user);
  console.log('🎯 Start param:', tg.initDataUnsafe?.start_param);
  console.log('📋 InitData:', tg.initData ? 'AVAILABLE' : 'MISSING');

  tg.expand();
  tg.enableClosingConfirmation();

  // Используем цвета темы Telegram
  const theme = tg.themeParams || {};
  const bgColor = theme.bg_color || '#0f1115';

  // прокидываем цвет фона в CSS-переменную
  try {
    document.documentElement.style.setProperty('--app-bg-color', bgColor);

    // определяем "темная / светлая" тема по яркости
    const hex = (theme.bg_color || '#000000').replace('#', '');
    const r = parseInt(hex.slice(0, 2) || '00', 16);
    const g = parseInt(hex.slice(2, 4) || '00', 16);
    const b = parseInt(hex.slice(4, 6) || '00', 16);
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const isDark = luminance < 140; // условный порог

    document.body.classList.toggle('theme-dark', isDark);
    document.body.classList.toggle('theme-light', !isDark);
  } catch (e) {
    console.log('Cannot compute theme darkness:', e);
  }

  // Спец. значение "bg_color" делает шапку такого же цвета, как фон Telegram
  tg.setHeaderColor('bg_color');
  tg.setBackgroundColor(bgColor);

  // На всякий случай синхронизируем фон body
  try {
    document.body.style.backgroundColor = bgColor;
  } catch (e) {
    console.log('Cannot set body background from theme:', e);
  }

  tg.ready();
  return true;
}

// Получаем start_param из URL или initData
function getStartParam() {
  console.log('🎯 [getStartParam] Starting parameter search...');

  // 1. Пробуем получить из URL
  try {
    const url = new URL(location.href);

    // 1.1. Классический параметр tgWebAppStartParam
    const urlParam = url.searchParams.get("tgWebAppStartParam");
    if (urlParam && urlParam !== 'demo') {
      console.log('🎯 [getStartParam] ✅ Got start_param from URL tgWebAppStartParam:', urlParam);

      if (urlParam.startsWith('results_')) {
        const gid = urlParam.replace('results_', '');
        console.log('🎯 [getStartParam] Results mode, gid:', gid);
        return gid;
      }

      return urlParam;
    }

    // 1.2. Прямой gid в URL (например, /miniapp/loading?gid=116)
    const gidParam = url.searchParams.get("gid");
    if (gidParam) {
      console.log('🎯 [getStartParam] ✅ Got gid from URL param "gid":', gidParam);

      if (gidParam.startsWith('results_')) {
        const gid = gidParam.replace('results_', '');
        console.log('🎯 [getStartParam] Results mode from gid param, gid:', gid);
        return gid;
      }

      return gidParam;
    }
  } catch (e) {
    console.log('[getStartParam] URL parse error:', e);
  }

  // 2. Пробуем получить из initData (на случай, если туда что-то зашито)
  try {
    const tg = window.Telegram?.WebApp;
    if (tg && tg.initDataUnsafe?.start_param) {
      const p = tg.initDataUnsafe.start_param;
      if (p && p !== 'demo') {
        console.log('🎯 [getStartParam] ✅ Got start_param from initData:', p);

        if (p.startsWith('results_')) {
          const gid = p.replace('results_', '');
          console.log('🎯 [getStartParam] Results mode from initData, gid:', gid);
          return gid;
        }

        return p;
      }
    }
  } catch (e) {
    console.log('[getStartParam] initData parse error:', e);
  }

  // 3. Fallback: берем из sessionStorage, куда уже пишет серверный /miniapp/ и loading
  try {
    const storedGid = sessionStorage.getItem('prizeme_gid');
    if (storedGid) {
      console.log('🎯 [getStartParam] ✅ Got gid from sessionStorage.prizeme_gid:', storedGid);

      if (storedGid.startsWith('results_')) {
        const gid = storedGid.replace('results_', '');
        console.log('[getStartParam] Results mode from sessionStorage, gid:', gid);
        return gid;
      }

      return storedGid;
    }
  } catch (e) {
    console.log('[getStartParam] sessionStorage error:', e);
  }

  console.log('❌ [getStartParam] No valid start_param/gid found');
  return null;
}


// Проверка завершения розыгрыша
async function checkGiveawayCompletion(gid) {
    try {
        console.log(`[COMPLETION-CHECK] Checking if giveaway ${gid} is completed`);
        
        const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
        if (!init_data) return false;
        
        const statusCheck = await api("/api/check_giveaway_status", { gid, init_data });
        console.log(`[COMPLETION-CHECK] Status response:`, statusCheck);
        
        return statusCheck.ok && statusCheck.is_completed;
    } catch (err) {
        console.error(`[COMPLETION-CHECK] Error:`, err);
        return false;
    }
}

// Проверка, нужно ли сразу открывать результаты
function checkImmediateResults() {
  try {
    // Уже на одном из экранов результатов — ничего не делаем
    if (
      window.location.pathname === '/miniapp/results_win' ||
      window.location.pathname === '/miniapp/results_lose'
    ) {
      console.log("[IMMEDIATE-RESULTS] Already on results page, skipping redirect");
      return false;
    }

    const url = new URL(location.href);
    const urlParam = url.searchParams.get("tgWebAppStartParam");

    if (urlParam && urlParam.startsWith('results_')) {
      const gid = urlParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] ✅ Redirecting to LOADING (results mode), gid:", gid);
      window.location.replace(`/miniapp/loading?gid=results_${encodeURIComponent(gid)}`);
      return true;
    }

    // Проверяем initData на случай запуска через startapp
    const initParam = tg.initDataUnsafe?.start_param;

    if (initParam && initParam.startsWith('results_')) {
      const gid = initParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] ✅ Redirecting to LOADING from initData (results mode), gid:", gid);
      window.location.replace(`/miniapp/loading?gid=results_${encodeURIComponent(gid)}`);
      return true;
    }
  } catch (e) {
    console.log("[IMMEDIATE-RESULTS] Error:", e);
  }

  return false;
}

// =========================
// RESULTS: определяем, победитель ли текущий юзер
// =========================
function isCurrentUserWinner(results, tgApp) {
  try {
    // 1) Прямой флаг (если бэк его кладет)
    if (results?.user?.is_winner === true) return true;

    // 2) Сверяем user_id победителей с текущим telegram user id
    const uid = tgApp?.initDataUnsafe?.user?.id;
    if (!uid) return false;

    const winners = Array.isArray(results?.winners) ? results.winners : [];
    return winners.some(w =>
      w?.is_current_user === true ||
      (w?.user_id != null && Number(w.user_id) === Number(uid))
    );
  } catch (e) {
    console.log("[RESULTS] isCurrentUserWinner error:", e);
    return false;
  }
}


// Универсальный вызов API
async function api(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {}),
    credentials: "include",
  });
  let payload = null;
  try { payload = await resp.json(); } catch {}
  if (!resp.ok) {
    const msg = (payload && payload.error) ? payload.error : (resp.status + " " + resp.statusText);
    throw new Error("API " + path + " failed: " + msg);
  }
  return payload || {};
}

// Функция для обновления счетчика времени
function updateCountdown(endAtUtc, elementId) {
    const countdownElement = document.getElementById(elementId);
    if (!countdownElement) {
        console.warn(`[COUNTDOWN] Элемент с ID '${elementId}' не найден.`);
        return;
    }

    // ИСПОЛЬЗУЕМ ФИКСИРОВАННУЮ ВЕРСИЮ ПАРСЕРА:
    function parseEndTime(value) {
        if (!value) return null;

        // Если уже Date – используем как есть
        if (value instanceof Date) return value;

        let raw = String(value).trim();
        if (!raw) return null;

        // 1) Пробуем как есть
        let d = new Date(raw);
        if (!isNaN(d.getTime())) return d;

        // 2) Формат "2025-11-20 20:00:00" → ISO
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(raw)) {
            d = new Date(raw.replace(' ', 'T') + 'Z');
            if (!isNaN(d.getTime())) return d;
        }

        // 3) Формат "2025-11-20T20:00:00" → добавляем Z
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(raw)) {
            d = new Date(raw + 'Z');
            if (!isNaN(d.getTime())) return d;
        }

        // 4) ФИКС: конвертируем UTC в MSK
        const mskDate = convertUTCtoMSK(raw);
        if (mskDate) return mskDate;

        return null;
    }

    const endTime = parseEndTime(endAtUtc);
    if (!endTime) {
        console.warn('[COUNTDOWN] Не удалось разобрать дату окончания:', endAtUtc);
        countdownElement.textContent = 'Дата окончания не указана';
        return;
    }

    function formatTimeLeft() {
        const now = new Date();
        const timeLeft = endTime.getTime() - now.getTime();

        if (!isFinite(timeLeft)) {
            countdownElement.textContent = 'Дата окончания не указана';
            return;
        }

        if (timeLeft <= 0) {
            countdownElement.textContent = 'Розыгрыш завершён';
            return;
        }

        const totalSeconds = Math.floor(timeLeft / 1000);
        const days = Math.floor(totalSeconds / (60 * 60 * 24));
        const hours = Math.floor((totalSeconds % (60 * 60 * 24)) / (60 * 60));
        const minutes = Math.floor((totalSeconds % (60 * 60)) / 60);
        const seconds = totalSeconds % 60;

        countdownElement.textContent =
            `${days} дн., ${String(hours).padStart(2, '0')}:` +
            `${String(minutes).padStart(2, '0')}:` +
            `${String(seconds).padStart(2, '0')}`;
    }

    // Первый расчёт + обновление раз в секунду
    formatTimeLeft();
    setInterval(formatTimeLeft, 1000);
}

// Функция для проверки, нужно ли открывать экран результатов
async function shouldShowResults(gid) {
  try {
    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) return false;
    
    const statusCheck = await api("/api/check_giveaway_status", { gid, init_data });
    console.log("[RESULTS] Status check:", statusCheck);
    
    return statusCheck.ok && statusCheck.is_completed;
  } catch (err) {
    console.error("[RESULTS] Status check error:", err);
    return false;
  }
}

// Основной поток проверки
async function checkFlow() {
  try {
    const gid = getStartParam();
    if (!gid) throw new Error("Empty start_param (gid)");

    console.log("[MULTI-PAGE] Starting check with gid:", gid);

    // Проверка Captcha перед основным потоком
    const requiresCaptcha = await checkCaptchaRequirement(gid);
    if (requiresCaptcha) {
      console.log("[CAPTCHA] Giveaway requires captcha verification");

      // ✅ Сначала проверяем выполнение условий (подписки) как в обычном флоу
      const tg = window.Telegram?.WebApp;
      let init_data = tg?.initData || '';

      if (!init_data) {
        const storedInit = sessionStorage.getItem('prizeme_init_data');
        if (storedInit) init_data = storedInit;
      }

      if (!init_data) {
        console.log("[CAPTCHA] No init_data, redirecting to need_subscription");
        sessionStorage.setItem('prizeme_gid', gid);
        window.location.href = '/miniapp/need_subscription';
        return;
      }

      const pre = await api("/api/check_membership_only", { gid, init_data });
      console.log("[CAPTCHA] Pre-check before captcha (membership only):", pre);

      if (!pre.ok) throw new Error("Membership pre-check failed");

      if (pre.need && pre.need.length > 0) {
        // отправляем на need_subscription
        sessionStorage.setItem('prizeme_gid', gid);
        sessionStorage.setItem('prizeme_init_data', init_data);
        sessionStorage.setItem('prizeme_need_data', JSON.stringify(pre.need || []));
        window.location.href = '/miniapp/need_subscription';
        return;
      }
      
      // Получаем site key для отображения Captcha
      const captchaSiteKey = await getCaptchaSiteKey();
      if (captchaSiteKey && captchaSiteKey !== "1x00000000000000000000AA") {
        // Сохраняем данные для Captcha проверки
        sessionStorage.setItem('prizeme_gid', gid);
        
        // Получаем init_data для использования на странице Captcha
        const tg = window.Telegram?.WebApp;
        let init_data = tg?.initData || '';
        if (init_data) {
          sessionStorage.setItem('prizeme_init_data', init_data);
        }
        
        // Сохраняем user_id (fallback для captcha.html)
        try {
          const uid = tg?.initDataUnsafe?.user?.id;
          if (uid) {
            sessionStorage.setItem('prizeme_user_id', String(uid));
          }
        } catch (e) {}

        // Редирект на страницу Captcha (будет создана позже)
        console.log("[CAPTCHA] Redirecting to captcha.html page");
        window.location.href = `/miniapp/captcha.html?gid=${encodeURIComponent(gid)}`;
        return;
      } else {
        // Captcha отключена или в тестовом режиме - продолжаем обычный flow
        console.log("[CAPTCHA] Captcha disabled or in test mode, continuing normal flow");
      }
    }

    // Получаем initData
    const tg = window.Telegram?.WebApp;
    let init_data = tg?.initData || '';

    // Fallback: если на этой странице Telegram не отдал initData,
    // берем его из sessionStorage, куда сохранил /miniapp/ при первом входе
    if (!init_data) {
      try {
        const storedInit = sessionStorage.getItem('prizeme_init_data');
        if (storedInit) {
          console.log("[MULTI-PAGE] Using init_data from sessionStorage.prizeme_init_data");
          init_data = storedInit;
        }
      } catch (e) {
        console.log("[MULTI-PAGE] sessionStorage init_data error:", e);
      }
    }
    
    console.log("[MULTI-PAGE] init_data available:", !!init_data);
    console.log("[MULTI-PAGE] Telegram WebApp available:", !!tg);

    if (!init_data) {
      throw new Error("Telegram WebApp not initialized. Please open through Telegram app.");
    }

    // 1) Проверяем условия
    const check = await api("/api/check", { gid, init_data });
    console.log("[MULTI-PAGE] Check response:", check);

    if (check.ok && check.done) {
      console.log("[MULTI-PAGE] Conditions met");
      
      if (check.ticket) {
        if (check.is_new_ticket) {
          // НОВЫЙ билет - редирект на экран успеха
          console.log("[MULTI-PAGE] Redirecting to SUCCESS screen");
          sessionStorage.setItem('prizeme_ticket', check.ticket);
          sessionStorage.setItem('prizeme_end_at', check.end_at_utc);
          window.location.href = '/miniapp/success';
        } else {
          // СУЩЕСТВУЮЩИЙ билет - редирект на экран "Уже участвуете"
          console.log("[MULTI-PAGE] Redirecting to ALREADY screen");
          sessionStorage.setItem('prizeme_ticket', check.ticket);
          sessionStorage.setItem('prizeme_end_at', check.end_at_utc);
          window.location.href = '/miniapp/already';
        }
      } else {
        // Нет билета - получаем новый через claim
        console.log("[MULTI-PAGE] No ticket, calling claim");
        const claim = await api("/api/claim", { gid, init_data });
        console.log("[MULTI-PAGE] Claim response:", claim);
        
        if (claim.ok && claim.ticket) {
          sessionStorage.setItem('prizeme_ticket', claim.ticket);
          sessionStorage.setItem('prizeme_end_at', claim.end_at_utc);
          window.location.href = '/miniapp/success';
        } else {
          throw new Error("Не удалось получить билет");
        }
      }
      return;
    }

    // 2) Нужно подписаться - редирект на экран подписки
    console.log("[MULTI-PAGE] Need subscription, redirecting to NEED screen");
    sessionStorage.setItem('prizeme_gid', gid);
    sessionStorage.setItem('prizeme_init_data', init_data);
    sessionStorage.setItem('prizeme_need_data', JSON.stringify(check.need || []));
    window.location.href = '/miniapp/need_subscription';

  } catch (err) {
    console.error("[MULTI-PAGE] checkFlow error:", err);
    sessionStorage.setItem('prizeme_error', err.message);
    window.location.href = '/miniapp/need_subscription';
  }
}

// Инициализация для главной страницы
function initializeMainPage() {
  console.log("[MULTI-PAGE] Initializing main page");
  
  const gid = getStartParam();
  console.log("[MULTI-PAGE] Extracted gid:", gid);
  
  // ДИАГНОСТИКА: логируем все доступные параметры
  try {
    const url = new URL(location.href);
    console.log("[MULTI-PAGE] Full URL:", location.href);
    console.log("[MULTI-PAGE] URL params:", Object.fromEntries(url.searchParams));
    console.log("[MULTI-PAGE] initDataUnsafe:", tg.initDataUnsafe);
  } catch (e) {
    console.log("[MULTI-PAGE] Diagnostic error:", e);
  }
  
  if (gid && gid !== 'demo') {
    // ЕСТЬ параметр розыгрыша - СРАЗУ запускаем flow участия (не показываем home_participant!)
    console.log("🎯 Giveaway ID found:", gid, "- Starting participation flow immediately");
    sessionStorage.setItem('prizeme_gid', gid);
    window.location.href = '/miniapp/loading';
  } else {
    // НЕТ параметра розыгрыша или demo - остаемся на home_participant
    console.log("❌ No giveaway ID or demo mode - staying on home participant page");
  }
}

// Инициализация для экрана загрузки
function initializeLoadingPage() {
  console.log('🎯 [LOADING] Initializing loading page');
  
  const gid = getStartParam();
  console.log('🎯 [LOADING] Extracted gid:', gid);
  
  if (!gid) {
    console.log('❌ [LOADING] No gid found, showing error');
    sessionStorage.setItem('prizeme_error', 'Empty start_param (gid). Please try again.');
    window.location.href = '/miniapp/need_subscription';
    return;
  }
  
  // Сохраняем gid в sessionStorage для резервной копии
  sessionStorage.setItem('prizeme_gid', gid);
  console.log('🎯 [LOADING] Saved gid to sessionStorage:', gid);
  
  // RESULTS MODE (results_XXX)
  if (gid && String(gid).startsWith("results_")) {
    const realGid = String(gid).replace("results_", "");
    console.log("[LOADING][RESULTS] Results mode detected, gid:", realGid);

    // Берем init_data как обычно
    const tgApp = window.Telegram?.WebApp;
    let init_data = tgApp?.initData || '';

    if (!init_data) {
      try {
        const storedInit = sessionStorage.getItem('prizeme_init_data');
        if (storedInit) init_data = storedInit;
      } catch (e) {}
    }

    if (!init_data) {
      console.log("[LOADING][RESULTS] No init_data, redirecting to index");
      window.location.href = '/miniapp/index';
      return;
    }

    (async () => {
      try {
        const results = await api("/api/results", { gid: parseInt(realGid, 10), init_data });
        console.log("[LOADING][RESULTS] /api/results response:", results);

        // Сохраняем, чтобы win/lose быстро отрисовались
        try { sessionStorage.setItem("prizeme_results", JSON.stringify(results)); } catch (e) {}

        const winner = isCurrentUserWinner(results, tgApp);
        console.log("[LOADING][RESULTS] winner =", winner);

        if (winner) {
          window.location.replace(`/miniapp/results_win?gid=${encodeURIComponent(realGid)}`);
        } else {
          window.location.replace(`/miniapp/results_lose?gid=${encodeURIComponent(realGid)}`);
        }
      } catch (e) {
        console.error("[LOADING][RESULTS] Failed to load results:", e);
        // Фоллбек — если API не ответил, ведем на lose
        window.location.replace(`/miniapp/results_lose?gid=${encodeURIComponent(realGid)}`);
      }
    })();

    return; // важно: не запускать checkFlow()
  }

  // Запускаем проверку через 1 секунду (дает время для инициализации)
  setTimeout(() => {
    checkFlow();
  }, 1000);
}

// Инициализация для экрана "Нужно подписаться"
function initializeNeedSubscriptionPage() {
  console.log("[NEED] Initializing need subscription page");

  const gidFromStorage = sessionStorage.getItem('prizeme_gid');
  const gid = gidFromStorage || getStartParam();
  const error = sessionStorage.getItem('prizeme_error') || null;

  let init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
  if (!init_data) {
    try {
      const storedInit = sessionStorage.getItem('prizeme_init_data');
      if (storedInit) {
        console.log("[NEED] Using init_data from sessionStorage.prizeme_init_data");
        init_data = storedInit;
      }
    } catch (e) {
      console.log("[NEED] sessionStorage init_data error:", e);
    }
  }

  if (!gid || !init_data) {
    console.warn("[NEED] No gid or init_data, cannot load channels");
    const list = document.getElementById('channels-list');
    if (list) {
      list.innerHTML = '<div class="organizers-note">Не удалось загрузить список каналов. Попробуйте открыть розыгрыш заново.</div>';
    }
    return;
  }

  if (error) {
    console.log("[NEED] Previous error:", error);
    // Ошибку можно залогировать, UI мы не ломаем – просто продолжаем загрузку каналов
  }

  loadNeedSubscriptionChannels(gid, init_data);
}

// Хелпер для идентификации канала (для сравнения в списке need)
function channelKey(ch) {
  if (!ch) return null;
  if (ch.id != null) return `id:${ch.id}`;
  if (ch.username) return `u:${String(ch.username).replace(/^@/, '')}`;
  if (ch.url) return `url:${ch.url}`;
  return null;
}

// Загрузка информации о каналах для экрана "Нужно подписаться"
async function loadNeedSubscriptionChannels(gid, init_data) {
  try {
    console.log("[NEED] Loading channels for gid:", gid);

    const checkData = await api("/api/check", { gid, init_data });
    console.log("[NEED] Check data:", checkData);

    if (!checkData.ok) {
      const list = document.getElementById('channels-list');
      if (list) {
        list.innerHTML = '<div class="organizers-note">Не удалось загрузить список каналов. Попробуйте позже.</div>';
      }
      return;
    }

    const allChannels =
      (checkData.channels && checkData.channels.length > 0)
        ? checkData.channels
        : (checkData.need || []);

    const needChannels = checkData.need || [];

    renderNeedChannels(allChannels, needChannels);
  } catch (err) {
    console.error("[NEED] Error loading need subscription channels:", err);
    const list = document.getElementById('channels-list');
    if (list) {
      list.innerHTML = '<div class="organizers-note">Произошла ошибка при загрузке каналов.</div>';
    }
  }
}

// Отрисовка каналов: "Подписаться" / "Подписан"
function renderNeedChannels(channels, needChannels) {
  const channelsList = document.getElementById('channels-list');
  if (!channelsList) return;

  channelsList.innerHTML = '';

  // Множество ключей каналов, на которые пользователь еще НЕ подписан
  const needKeys = new Set(
    (needChannels || [])
      .map(channelKey)
      .filter(Boolean)
  );

  channels.forEach(channel => {
    const key = channelKey(channel);
    const isNeed = key ? needKeys.has(key) : false;

    const title = channel.title || 'Канал';
    const username = channel.username
      ? String(channel.username).replace(/^@/, '')
      : null;

    const url = channel.url || (username ? `https://t.me/${username}` : '#');
    const firstLetter = title.charAt(0).toUpperCase();

    const safeUrl = url.replace(/'/g, "\\'"); // чтобы не сломать HTML

    const buttonHtml = isNeed
      ? `<button class="channel-button subscribe" onclick="openChannel('${safeUrl}')">Подписаться</button>`
      : `<button class="channel-button subscribed" disabled aria-disabled="true">Подписан</button>`;

    const card = document.createElement('div');
    card.className = 'channel-card';

    card.innerHTML = `
      <div class="channel-avatar">${firstLetter}</div>
      <div class="channel-info">
        <div class="channel-name">${title}</div>
        ${username ? `<div class="channel-username">@${username}</div>` : ''}
      </div>
      ${buttonHtml}
    `;

    channelsList.appendChild(card);
  });
}

// Глобальная функция открытия канала / группы Telegram
function openChannel(url) {
  try {
    if (!url || url === '#') {
      console.log('[LINK] Empty or invalid URL for openChannel:', url);
      return;
    }

    // Если доступен WebApp API — открываем внутри Telegram
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openTelegramLink) {
      Telegram.WebApp.openTelegramLink(url);
    } else {
      // Фоллбек — новое окно/вкладка
      window.open(url, '_blank');
    }
  } catch (error) {
    console.log('[LINK] Error opening channel:', error);
    try {
      if (url && url !== '#') {
        window.open(url, '_blank');
      }
    } catch (e) {
      console.log('[LINK] Fallback open error:', e);
    }
  }
}

function getQueryParam(name) {
  try {
    return new URLSearchParams(window.location.search).get(name);
  } catch (e) {
    return null;
  }
}

async function ensureEndAtInStorage(gid) {
  try {
    if (!gid) return;

    // если уже есть — ничего не делаем
    const existing = sessionStorage.getItem('prizeme_end_at');
    if (existing) return;

    let init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) {
      const storedInit = sessionStorage.getItem('prizeme_init_data');
      if (storedInit) init_data = storedInit;
    }
    if (!init_data) return;

    const resp = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gid: parseInt(gid, 10), init_data })
    });

    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data && data.end_at_utc) {
      sessionStorage.setItem('prizeme_end_at', data.end_at_utc);
      console.log('[END_AT] Stored end_at_utc:', data.end_at_utc);
    }
  } catch (e) {
    console.error('[END_AT] Failed to ensure end_at:', e);
  }
}


// Инициализация для экрана "Успех"
async function initializeSuccessPage() {
  console.log("[SUCCESS] Initializing new success page");
  
  let ticket = sessionStorage.getItem('prizeme_ticket');
  let endAt  = sessionStorage.getItem('prizeme_end_at');
  let gid    = sessionStorage.getItem('prizeme_gid');

  const ticketFromUrl = getQueryParam('ticket_code');
  const gidFromUrl = getQueryParam('gid');

  if (!gid && gidFromUrl) {
    gid = gidFromUrl;
    sessionStorage.setItem('prizeme_gid', gid);
  }

  if (!ticket && ticketFromUrl) {
    ticket = ticketFromUrl;
    sessionStorage.setItem('prizeme_ticket', ticket);
  }

  await ensureEndAtInStorage(gid);
  endAt = sessionStorage.getItem('prizeme_end_at');
  
  // Устанавливаем номер билета
  if (ticket) {
    const ticketElement = document.getElementById('ticket-number');
    if (ticketElement) {
      ticketElement.textContent = ticket;
    }
  }
  
  // Запускаем обновленный счетчик
  if (endAt) {
    updateNewCountdown(endAt);
  }
  
  // Загружаем информацию о каналах
  if (gid) {
    loadChannelsInfo(gid);
  }
  
  // Очищаем storage после использования
  sessionStorage.removeItem('prizeme_ticket');
  sessionStorage.removeItem('prizeme_end_at');
  sessionStorage.removeItem('prizeme_gid');
  sessionStorage.removeItem('prizeme_init_data');
}

// Новая функция для счетчика с 4 квадратами
function updateNewCountdown(endAtUtc) {
  const daysElement = document.getElementById('countdown-days');
  const hoursElement = document.getElementById('countdown-hours');
  const minutesElement = document.getElementById('countdown-minutes');
  const secondsElement = document.getElementById('countdown-seconds');
  
  if (!daysElement || !hoursElement || !minutesElement || !secondsElement) {
    console.warn('[COUNTDOWN] One or more countdown elements not found');
    return;
  }

  function parseEndTime(value) {
    if (!value) return null;
    if (value instanceof Date) return value;

    let raw = String(value).trim();
    if (!raw) return null;

    // 1) Пробуем как есть
    let d = new Date(raw);
    if (!isNaN(d.getTime())) return d;

    // 2) Формат "2025-11-20 20:00:00" → ISO
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(raw)) {
      d = new Date(raw.replace(' ', 'T') + 'Z');
      if (!isNaN(d.getTime())) return d;
    }

    // 3) Формат "2025-11-20T20:00:00" → добавляем Z
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(raw)) {
      d = new Date(raw + 'Z');
      if (!isNaN(d.getTime())) return d;
    }

    // 4) ФИКС: конвертируем UTC в MSK
    const mskDate = convertUTCtoMSK(raw);
    if (mskDate) return mskDate;

    return null;
  }

  const endTime = parseEndTime(endAtUtc);
  if (!endTime) {
    console.warn('[COUNTDOWN] Не удалось разобрать дату окончания:', endAtUtc);
    daysElement.textContent = '00';
    hoursElement.textContent = '00';
    minutesElement.textContent = '00';
    secondsElement.textContent = '00';
    return;
  }

  function formatTimeLeft() {
    const now = new Date();
    const timeLeft = endTime.getTime() - now.getTime();

    if (!isFinite(timeLeft)) {
      daysElement.textContent = '00';
      hoursElement.textContent = '00';
      minutesElement.textContent = '00';
      secondsElement.textContent = '00';
      return;
    }

    if (timeLeft <= 0) {
      daysElement.textContent = '00';
      hoursElement.textContent = '00';
      minutesElement.textContent = '00';
      secondsElement.textContent = '00';
      return;
    }

    const totalSeconds = Math.floor(timeLeft / 1000);
    const days = Math.floor(totalSeconds / (60 * 60 * 24));
    const hours = Math.floor((totalSeconds % (60 * 60 * 24)) / (60 * 60));
    const minutes = Math.floor((totalSeconds % (60 * 60)) / 60);
    const seconds = totalSeconds % 60;

    daysElement.textContent = String(days).padStart(2, '0');
    hoursElement.textContent = String(hours).padStart(2, '0');
    minutesElement.textContent = String(minutes).padStart(2, '0');
    secondsElement.textContent = String(seconds).padStart(2, '0');
  }

  // Первый расчёт + обновление раз в секунду
  formatTimeLeft();
  setInterval(formatTimeLeft, 1000);
}

// Функция для загрузки информации о каналах
async function loadChannelsInfo(gid) {
  try {
    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) {
      console.warn('[CHANNELS] No init data available');
      return;
    }

    // Получаем информацию о розыгрыше через API check
    const checkData = await api("/api/check", { gid, init_data });
    console.log('[CHANNELS] Check data:', checkData);

    if (!checkData.ok) {
      return;
    }

    // Если есть need (пользователь не подписан) — показываем их.
    // Если need пустой — показываем полный список organizer-каналов.
    const channelsSource =
      (checkData.need && checkData.need.length > 0)
        ? checkData.need
        : (checkData.channels || []);

    if (channelsSource && channelsSource.length > 0) {
      displayChannels(channelsSource);
    }
  } catch (error) {
    console.error('[CHANNELS] Error loading channels:', error);
  }
}

// Функция для отображения каналов
function displayChannels(channels) {
  const channelsList = document.getElementById('channels-list');
  if (!channelsList) return;

  channelsList.innerHTML = '';

  channels.forEach(channel => {
    const channelCard = document.createElement('div');
    channelCard.className = 'channel-card';

    const title = channel.title || 'Канал';
    const username = channel.username
      ? String(channel.username).replace(/^@/, '')
      : null;

    // URL: либо пришёл с бэка, либо собираем из username, иначе заглушка "#"
    const url = channel.url || (username ? `https://t.me/${username}` : '#');

    // Аватарка — первая буква названия
    const firstLetter = title.charAt(0).toUpperCase();

    channelCard.innerHTML = `
      <div class="channel-avatar">${firstLetter}</div>
      <div class="channel-info">
        <div class="channel-name">${title}</div>
        ${username ? `<div class="channel-username">@${username}</div>` : ''}
      </div>
      <button class="channel-button" onclick="openChannel('${url}')">
        Перейти
      </button>
    `;

    channelsList.appendChild(channelCard);
  });
}

// Функция конвертации UTC в MSK (добавьте если нет)
function convertUTCtoMSK(utcDateString) {
  try {
    if (!utcDateString) return null;
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


// Функции для работы с Captcha - Проверяет, требуется ли Captcha для розыгрыша
async function checkCaptchaRequirement(giveawayId) {
  console.log('[CAPTCHA] Checking requirement for giveaway', giveawayId);
  
  try {
    // Реальная проверка через Node.js API
    const response = await fetch('/api/requires_captcha', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ giveaway_id: giveawayId })
    });
    
    if (!response.ok) {
      console.error('[CAPTCHA] Error response:', response.status);
      return false;
    }
    
    const data = await response.json();
    console.log('[CAPTCHA] Captcha requirement check result:', data);
    return data.requires_captcha || false;
    
  } catch (error) {
    console.error('[CAPTCHA] Error checking requirement:', error);
    return false;
  }
}

// Получает публичный ключ Captcha с сервера
async function getCaptchaSiteKey() {
  try {
    // 🔄 Делаем запрос к API для получения ключа Captcha
    const response = await fetch("/api/captcha_config", {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });
    
    if (response.ok) {
      const data = await response.json();
      console.log("[CAPTCHA] Site key response:", data);
      return data.site_key || null;
    }
    
    console.log("[CAPTCHA] Failed to get site key, using default");
    return null;
    
  } catch (error) {
    console.error("[CAPTCHA] Error getting site key:", error);
    return null;
  }
}

// Проверяет токен Captcha через API
async function verifyCaptchaToken(token, giveawayId) {
  try {
    console.log(`[CAPTCHA] Verifying token for giveaway ${giveawayId}`);
    
    const response = await fetch("/api/verify_captcha", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: token,
        giveaway_id: giveawayId
      })
    });
    
    const result = await response.json();
    console.log("[CAPTCHA] Verification result:", result);
    
    return result.ok === true;
    
  } catch (error) {
    console.error("[CAPTCHA] Error verifying token:", error);
    // В случае ошибки лучше пропустить проверку
    return true;
  }
}

// Обрабатывает успешное прохождение Captcha
function handleCaptchaSuccess(giveawayId, token) {
  console.log(`[CAPTCHA] Success for giveaway ${giveawayId}`);
  
  // 🔄 Сохраняем токен в sessionStorage для использования в основном flow
  sessionStorage.setItem('prizeme_captcha_token', token);
  sessionStorage.setItem('prizeme_captcha_verified', 'true');
  
  // 🔄 Возвращаем к основному flow
  window.location.href = '/miniapp/loading';
}

// Инициализация для экрана "Уже участвуете"
async function initializeAlreadyPage() {
  console.log("[ALREADY] Initializing already page");

  let ticket = sessionStorage.getItem('prizeme_ticket');
  let endAt  = sessionStorage.getItem('prizeme_end_at');
  let gid    = sessionStorage.getItem('prizeme_gid');

  // ✅ Fallback из URL (когда пришли после captcha-redirect)
  const ticketFromUrl = getQueryParam('ticket_code');
  const gidFromUrl = getQueryParam('gid');

  if (!gid && gidFromUrl) {
    gid = gidFromUrl;
    sessionStorage.setItem('prizeme_gid', gid);
  }

  if (!ticket && ticketFromUrl) {
    ticket = ticketFromUrl;
    sessionStorage.setItem('prizeme_ticket', ticket);
  }

  // ✅ если endAt нет — попробуем догрузить через /api/check
  await ensureEndAtInStorage(gid);
  endAt = sessionStorage.getItem('prizeme_end_at');

  // 1. Номер билета — те же ID, что на success
  const ticketElement = document.getElementById('ticket-number');
  if (ticket && ticketElement) {
    ticketElement.textContent = ticket;
  }

  // 2. Таймер в 4 квадрата (как на success)
  if (endAt) {
    updateNewCountdown(endAt);
  }

  // 3. Блок организаторов — грузим те же данные, что на success
  if (gid) {
    loadChannelsInfo(gid);
  }

  // 4. После инициализации чистим сторедж
  sessionStorage.removeItem('prizeme_ticket');
  sessionStorage.removeItem('prizeme_end_at');
  sessionStorage.removeItem('prizeme_gid');
  sessionStorage.removeItem('prizeme_init_data');
}

// =========================
// ЭКРАН РЕЗУЛЬТАТОВ — ПОБЕДА
// =========================

function initializeResultsWinPage() {
  console.log("[RESULTS-WIN] Initializing results win page");

  const urlParams = new URLSearchParams(window.location.search);
  const gid = urlParams.get('gid');

  // Пробуем сначала взять результаты из sessionStorage,
  // которые мог положить results.html перед редиректом.
  let stored = null;
  try {
    const raw = sessionStorage.getItem('prizeme_results');
    if (raw) {
      stored = JSON.parse(raw);
      console.log("[RESULTS-WIN] Using stored results from sessionStorage");
    }
  } catch (e) {
    console.log("[RESULTS-WIN] Failed to parse stored results:", e);
  }

  if (stored) {
    const tgApp = window.Telegram?.WebApp;
    const winner = isCurrentUserWinner(stored, tgApp);
    if (!winner) {
      console.log("[RESULTS-WIN] Stored says NOT winner, redirecting to lose");
      window.location.replace(`/miniapp/results_lose?gid=${gid || ''}`);
      return;
    }
    renderResultsWin(stored);
    return;
  }

  // Если в storage ничего нет — фоллбек, грузим результаты напрямую
  if (!gid) {
    console.warn("[RESULTS-WIN] No gid in URL and no stored results");
    showWinError("Не удалось загрузить результаты розыгрыша");
    return;
  }

  fetchResultsForWin(gid);
}

async function fetchResultsForWin(gid) {
  try {
    console.log("[RESULTS-WIN] Fetching results for gid:", gid);

    const init_data =
      (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";

    if (!init_data) {
      throw new Error("Не удалось получить данные авторизации");
    }

    const results = await api("/api/results", { gid, init_data });
    console.log("[RESULTS-WIN] API /api/results response:", results);

    if (!results.ok) {
      throw new Error(results.reason || "Не удалось загрузить результаты");
    }

    // Сохраняем на всякий случай
    try {
      sessionStorage.setItem("prizeme_results", JSON.stringify(results));
    } catch (e) {
      console.log("[RESULTS-WIN] Cannot store results in sessionStorage:", e);
    }

    // Если пользователь НЕ победитель — сразу уводим на экран проигрыша
    if (!results.user || !results.user.is_winner) {
      console.log("[RESULTS-WIN] User is not a winner according to results, redirecting to results_lose");
      window.location.replace(`/miniapp/results_lose?gid=${gid}`);
      return;
    }

    // Иначе — отрисовываем экран победителя
    renderResultsWin(results);

  } catch (err) {
    console.error("[RESULTS-WIN] Error fetching results:", err);
    showWinError(err.message || "Ошибка загрузки результатов");
  }
}

function renderResultsWin(data) {
  console.log("[RESULTS-WIN] Rendering results win screen with data:", data);

  // Название розыгрыша
  const titleEl = document.getElementById("results-win-giveaway-title");
  if (titleEl) {
    titleEl.textContent = (data.giveaway && data.giveaway.title) || "Розыгрыш";
  }

  // Список победителей
  const winnersList = document.getElementById("winners-list");
  if (!winnersList) {
    console.warn("[RESULTS-WIN] #winners-list not found");
    return;
  }

  winnersList.innerHTML = "";

  const winners = Array.isArray(data.winners) ? data.winners : [];

  if (!winners.length) {
    const empty = document.createElement("div");
    empty.className = "winner-card";
    empty.innerHTML = `
      <div class="winner-avatar"></div>
      <div class="winner-info">
        <div class="winner-name">Победители не найдены</div>
        <div class="winner-ticket"></div>
      </div>
    `;
    winnersList.appendChild(empty);
    return;
  }

  winners.forEach((winner, index) => {
    let nickname =
      winner.username ||
      winner.display_name ||
      `Победитель #${winner.rank || ""}`.trim();

    if (nickname && !nickname.startsWith('@')) {
      nickname = '@' + nickname.replace(/^@/, '');
    }

    const isCurrentUser = !!winner.is_current_user;
    const ticketCode = winner.ticket_code || "";
    const ticketLabel = "Номер билета";

    // Позиция победителя: сначала пробуем rank, если его нет — индекс + 1
    const position = winner.rank || (index + 1);

    let avatarContent = "";

    if (position === 1) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/gold-medal-image.webp"
          alt="1 место"
          class="winner-medal"
        />
      `;
    } else if (position === 2) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/silver-medal-image.webp"
          alt="2 место"
          class="winner-medal"
        />
      `;
    } else if (position === 3) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/bronze-medal-image.webp"
          alt="3 место"
          class="winner-medal"
        />
      `;
    } else {
      avatarContent = `<span class="winner-position">${position}</span>`;
    }

    const card = document.createElement("div");
    card.className = "winner-card" + (isCurrentUser ? " current-user" : "");

    card.innerHTML = `
      <div class="winner-avatar">
        ${avatarContent}
      </div>
      <div class="winner-info">
        <div class="winner-name">${nickname}</div>
        <div class="winner-ticket">${ticketLabel}: ${ticketCode}</div>
      </div>
    `;

    winnersList.appendChild(card);
  });
}

function showWinError(message) {
  console.log("[RESULTS-WIN] showWinError:", message);
  const titleEl = document.getElementById("results-win-giveaway-title");
  if (titleEl) {
    titleEl.textContent = message || "Ошибка загрузки результатов";
  }
}


// Определяем текущую страницу и инициализируем соответствующую логику
function initializeCurrentPage() {
  const path = window.location.pathname;
  console.log("[MULTI-PAGE] Current path:", path);
  
  // Инициализируем Telegram WebApp на ВСЕХ страницах
  const tgInitialized = initializeTelegramWebApp();
  if (!tgInitialized) {
    console.error('❌ Cannot initialize Telegram WebApp');
  }

  // Проверяем немедленный редирект на результаты,
  // если мы НЕ уже на одном из экранов результатов
  if (
    path !== '/miniapp/results_win' &&
    path !== '/miniapp/results_lose' &&
    checkImmediateResults()
  ) {
    return;
  }

  switch (path) {
      case '/miniapp/':
          initializeMainPage();
          break;

      case '/miniapp/home_participant':
      case '/miniapp/home_creator':
      case '/miniapp/index':  // <--- ДОБАВЛЯЕМ ЭТОТ КЕЙС!
          // Главные экраны участника/создателя.
          // Telegram WebApp уже инициализирован выше,
          // дальше логика отдается отдельным js (main.js для SPA)
          console.log("[MULTI-PAGE] Home screen page (/index), SPA will handle it");
          break;

      case '/miniapp/loading':
          initializeLoadingPage();
          break;
      case '/miniapp/need_subscription':
          initializeNeedSubscriptionPage();
          break;
      case '/miniapp/captcha':
          // Страница Captcha - логика в captcha.html
          console.log("[MULTI-PAGE] Captcha page, letting captcha.html handle it");
          break;
      case '/miniapp/success':
          initializeSuccessPage();
          break;
      case '/miniapp/already':
          initializeAlreadyPage();
          break;
      case '/miniapp/results_win':
          initializeResultsWinPage();
          break;
      case '/miniapp/results_lose':
          initializeResultsLosePage();
          break;
      default: {
          // ✅ Разрешаем статические страницы (не SPA), чтобы роутер их НЕ редиректил на index
          const allowedStaticPages = new Set([
              '/miniapp/success.html',
              '/miniapp/already_participating.html',
              '/miniapp/captcha.html'
          ]);

          if (allowedStaticPages.has(path)) {
            console.log('[MULTI-PAGE] Allowed static page, skipping SPA redirect:', path);

            // ✅ Запускаем нужную инициализацию для статических страниц
            if (path === '/miniapp/success.html') {
              initializeSuccessPage();
            } else if (path === '/miniapp/already_participating.html') {
              initializeAlreadyPage();
            }
            // captcha.html сам инициализируется своим captcha.js
            return;
          }

          // Для неизвестных путей редиректим на главную SPA
          if (path.startsWith('/miniapp/')) {
              console.log("[MULTI-PAGE] Unknown miniapp path, redirecting to index:", path);
              window.location.href = '/miniapp/index';
          } else {
              console.log("[MULTI-PAGE] Not a miniapp path, staying on:", path);
          }
          break;
      }
  }
}

// Запускаем приложение
document.addEventListener("DOMContentLoaded", initializeCurrentPage);

// Автоматическая перепроверка при возвращении из Telegram
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && 
      window.location.pathname === '/miniapp/need_subscription') {
    console.log("[MULTI-PAGE] Visibility changed, reloading check");
    sessionStorage.removeItem('prizeme_error');
    sessionStorage.removeItem('prizeme_need_data');
    window.location.href = '/miniapp/loading';
  }
});

// =========================
// ЭКРАН РЕЗУЛЬТАТОВ — ПРОИГРЫШ
// =========================

function initializeResultsLosePage() {
  console.log("[RESULTS-LOSE] Initializing results lose page");

  const urlParams = new URLSearchParams(window.location.search);
  const gid = urlParams.get('gid');

  // Пробуем взять результаты из sessionStorage (как для win)
  let stored = null;
  try {
    const raw = sessionStorage.getItem("prizeme_results");
    if (raw) {
      stored = JSON.parse(raw);
      console.log("[RESULTS-LOSE] Using stored results from sessionStorage");
    }
  } catch (e) {
    console.log("[RESULTS-LOSE] Failed to parse stored results:", e);
  }

  // Если есть сохранённые результаты и пользователь НЕ победитель — рендерим сразу
  if (stored) {
    const tgApp = window.Telegram?.WebApp;
    const winner = isCurrentUserWinner(stored, tgApp);
    if (winner) {
      console.log("[RESULTS-LOSE] Stored says WINNER, redirecting to win");
      window.location.replace(`/miniapp/results_win?gid=${gid || ''}`);
      return;
    }
    renderResultsLose(stored);
    return;
  }

  if (!gid) {
    console.warn("[RESULTS-LOSE] No gid in URL and no stored results");
    showLoseError("Не удалось загрузить результаты розыгрыша");
    return;
  }

  fetchResultsForLose(gid);
}

async function fetchResultsForLose(gid) {
  try {
    console.log("[RESULTS-LOSE] Fetching results for gid:", gid);

    const init_data =
      (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";

    if (!init_data) {
      throw new Error("Не удалось получить данные авторизации");
    }

    const results = await api("/api/results", { gid, init_data });
    console.log("[RESULTS-LOSE] API /api/results response:", results);

    if (!results.ok) {
      throw new Error(results.reason || "Не удалось загрузить результаты");
    }

    // Сохраняем результаты
    try {
      sessionStorage.setItem("prizeme_results", JSON.stringify(results));
    } catch (e) {
      console.log("[RESULTS-LOSE] Cannot store results in sessionStorage:", e);
    }

    // Если розыгрыш ещё не завершён
    if (results.finished === false) {
      showLoseError(results.message || "Розыгрыш ещё не завершен. Результаты будут позже.");
      return;
    }

    // Если пользователь всё-таки победитель — отправляем на экран победы
    if (results.user && results.user.is_winner) {
      console.log("[RESULTS-LOSE] User is winner according to results, redirecting to results_win");
      window.location.replace(`/miniapp/results_win?gid=${gid}`);
      return;
    }

    renderResultsLose(results);
  } catch (err) {
    console.error("[RESULTS-LOSE] Error fetching results:", err);
    showLoseError(err.message || "Ошибка загрузки результатов");
  }
}

function renderResultsLose(data) {
  console.log("[RESULTS-LOSE] Rendering results lose screen with data:", data);

  // Название розыгрыша
  const titleEl = document.getElementById("results-lose-giveaway-title");
  if (titleEl) {
    titleEl.textContent = (data.giveaway && data.giveaway.title) || "Розыгрыш";
  }

  // Список победителей
  const winnersList = document.getElementById("winners-list");
  if (!winnersList) {
    console.warn("[RESULTS-LOSE] #winners-list not found");
    return;
  }

  winnersList.innerHTML = "";

  const winners = Array.isArray(data.winners) ? data.winners : [];

  if (!winners.length) {
    const empty = document.createElement("div");
    empty.className = "winner-card";
    empty.innerHTML = `
      <div class="winner-avatar"></div>
      <div class="winner-info">
        <div class="winner-name">Победители не найдены</div>
        <div class="winner-ticket"></div>
      </div>
    `;
    winnersList.appendChild(empty);
    return;
  }

  winners.forEach((winner, index) => {
    let nickname =
      winner.username ||
      winner.display_name ||
      `Победитель #${winner.rank || ""}`.trim();

    if (nickname && !nickname.startsWith("@")) {
      nickname = "@" + nickname.replace(/^@/, "");
    }

    const ticketCode = winner.ticket_code || "";
    const ticketLabel = "Номер билета";

    // Позиция победителя
    const position = winner.rank || (index + 1);

    let avatarContent = "";

    if (position === 1) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/gold-medal-image.webp"
          alt="1 место"
          class="winner-medal"
        />
      `;
    } else if (position === 2) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/silver-medal-image.webp"
          alt="2 место"
          class="winner-medal"
        />
      `;
    } else if (position === 3) {
      avatarContent = `
        <img
          src="/miniapp-static/assets/images/bronze-medal-image.webp"
          alt="3 место"
          class="winner-medal"
        />
      `;
    } else {
      avatarContent = `<span class="winner-position">${position}</span>`;
    }

    const card = document.createElement("div");
    // Для экрана проигрыша — БЕЗ current-user, чтобы не было белой рамки
    card.className = "winner-card";

    card.innerHTML = `
      <div class="winner-avatar">
        ${avatarContent}
      </div>
      <div class="winner-info">
        <div class="winner-name">${nickname}</div>
        <div class="winner-ticket">${ticketLabel}: ${ticketCode}</div>
      </div>
    `;

    winnersList.appendChild(card);
  });
}

function showLoseError(message) {
  console.log("[RESULTS-LOSE] showLoseError:", message);
  const titleEl = document.getElementById("results-lose-giveaway-title");
  if (titleEl) {
    titleEl.textContent = message || "Ошибка загрузки результатов";
  }
}