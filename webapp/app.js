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

  // Расширяем на весь экран
  tg.expand();
  
  // Отключаем подтверждение закрытия
  tg.enableClosingConfirmation();
  
  // Устанавливаем цвета
  tg.setHeaderColor('#2481cc');
  tg.setBackgroundColor('#f4f4f5');
  
  // Говорим Telegram что приложение готово
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
    // Проверяем, не находимся ли мы уже на results
    if (window.location.pathname === '/miniapp/results') {
      console.log("[IMMEDIATE-RESULTS] Already on results page, skipping redirect");
      return false;
    }
    
    const url = new URL(location.href);
    const urlParam = url.searchParams.get("tgWebAppStartParam");
    
    if (urlParam && urlParam.startsWith('results_')) {
      const gid = urlParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] 🎲 Immediately redirecting to results for gid:", gid);
      // Используем replace вместо href чтобы избежать истории навигации
      window.location.replace(`/miniapp/results?gid=${gid}`);
      return true;
    }
    
    // Проверяем initData для результатов
    const initParam = tg.initDataUnsafe?.start_param;
    if (initParam && initParam.startsWith('results_')) {
      const gid = initParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] 🎲 Immediately redirecting to results from initData, gid:", gid);
      // Используем replace вместо href
      window.location.replace(`/miniapp/results?gid=${gid}`);
      return true;
    }
  } catch (e) {
    console.log("[IMMEDIATE-RESULTS] Error:", e);
  }
  
  return false;
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
    
    // Настройка Telegram WebApp
    if (window.Telegram && Telegram.WebApp) {
      Telegram.WebApp.expand();
      Telegram.WebApp.enableClosingConfirmation();
      Telegram.WebApp.setHeaderColor('#2481cc');
      Telegram.WebApp.setBackgroundColor('#f4f4f5');
      Telegram.WebApp.ready();
    }
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


// Инициализация для экрана "Успех"
function initializeSuccessPage() {
  console.log("[SUCCESS] Initializing new success page");
  
  const ticket = sessionStorage.getItem('prizeme_ticket');
  const endAt = sessionStorage.getItem('prizeme_end_at');
  const gid = sessionStorage.getItem('prizeme_gid');
  
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

// Инициализация для экрана "Уже участвуете"
function initializeAlreadyPage() {
  console.log("[ALREADY] Initializing already page");

  const ticket = sessionStorage.getItem('prizeme_ticket');
  const endAt = sessionStorage.getItem('prizeme_end_at');
  const gid    = sessionStorage.getItem('prizeme_gid');

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

// Определяем текущую страницу и инициализируем соответствующую логику
function initializeCurrentPage() {
  const path = window.location.pathname;
  console.log("[MULTI-PAGE] Current path:", path);
  
  // Инициализируем Telegram WebApp на ВСЕХ страницах
  const tgInitialized = initializeTelegramWebApp();
  if (!tgInitialized) {
    console.error('❌ Cannot initialize Telegram WebApp');
  }

  // Проверяем немедленный редирект на результаты ТОЛЬКО если мы НЕ на странице результатов
  if (path !== '/miniapp/results' && checkImmediateResults()) {
    return;
  }
  
  switch(path) {
    case '/miniapp/':
      initializeMainPage();
      break;
    case '/miniapp/loading':
      initializeLoadingPage();
      break;
    case '/miniapp/need_subscription':
      initializeNeedSubscriptionPage();
      break;
    case '/miniapp/success':
      initializeSuccessPage();
      break;
    case '/miniapp/already':
      initializeAlreadyPage();
      break;
    case '/miniapp/results':
      initializeResultsPage();
      break;
    default:
      window.location.href = '/miniapp/';
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

// Добавляем новую функцию инициализации для экрана результатов
function initializeResultsPage() {
  console.log("[MULTI-PAGE] Initializing results page");
  
  // Показываем экран загрузки, скрываем остальные
  hide("#screen-results");
  hide("#screen-error");
  show("#screen-loading");
  
  // Получаем параметры из URL
  const urlParams = new URLSearchParams(window.location.search);
  const gid = urlParams.get('gid');
  
  if (!gid) {
    showError("Не указан идентификатор розыгрыша");
    return;
  }
  
  // Загружаем результаты
  loadResults(gid);
  
  // Настройка кнопок
  $("#btn-back").onclick = () => {
    window.history.back();
  };
  
  $("#btn-retry").onclick = () => {
    hide("#screen-error");
    show("#screen-loading");
    loadResults(gid);
  };
}

// Функция загрузки результатов
async function loadResults(gid) {
  try {
    console.log("[RESULTS] 🔄 Начинаем загрузку результатов для gid:", gid);
    
    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) {
      throw new Error("Не удалось получить данные авторизации");
    }
    
    const results = await api("/api/results", { gid, init_data });
    console.log("[RESULTS] 📊 Получены результаты:", results);
    
    if (results.ok) {
      // 🔧 ФИКС: УБИРАЕМ ЦИКЛИЧЕСКУЮ ПЕРЕЗАГРУЗКУ
      // Вместо автоматического редиректа - просто показываем статус
      if (results.finished === false) {
        // Розыгрыш еще не завершен - показываем сообщение БЕЗ перезагрузки
        showNotFinished(results.message || "Розыгрыш еще не завершен");
      } else if (results.noWinners || (results.winners && results.winners.length === 0)) {
        // Нет победителей
        showNoWinners(results);
      } else {
        // Есть победители
        displayResults(results);
      }
    } else {
      throw new Error(results.reason || "Не удалось загрузить результаты");
    }
    
  } catch (err) {
    console.error("[RESULTS] ❌ Ошибка загрузки результатов:", err);
    showError(err.message);
  }
}

// ФУНКЦИЯ ДЛЯ "РОЗЫГРЫШ НЕ ЗАВЕРШЕН":
function showNotFinished(message) {
  hide("#screen-loading");
  show("#screen-results");
  
  $("#giveaway-title").textContent = "Розыгрыш еще не завершен";
  $("#giveaway-description").textContent = message || "Ожидайте определения победителей";
  
  const winnerStatusElement = $("#winner-status");
  winnerStatusElement.innerHTML = `
    <div class="status-message status-not-finished">
      ⏳ Розыгрыш еще не завершен<br><br>
      ${message || "Результаты будут доступны после окончания розыгрыша."}
    </div>
  `;
  
  $("#winners-section").style.display = 'none';
  $("#no-winners").style.display = 'none';
  
  // УБИРАЕМ КНОПКУ "НАЗАД" ЕСЛИ НУЖНО
  $("#btn-back").style.display = 'block';
}

// ФУНКЦИЯ ДЛЯ "НЕТ ПОБЕДИТЕЛЕЙ":
function showNoWinners(data) {
  hide("#screen-loading");
  show("#screen-results");
  
  $("#giveaway-title").textContent = data.giveaway?.title || "Розыгрыш завершен";
  $("#giveaway-description").textContent = data.giveaway?.description || "Описание отсутствует";
  $("#participants-count").textContent = data.giveaway?.participants_count || 0;
  $("#winners-count").textContent = data.giveaway?.winners_count || 0;
  
  const winnerStatusElement = $("#winner-status");
  winnerStatusElement.innerHTML = `
    <div class="status-message status-no-winners">
      🎉 Розыгрыш завершен!<br><br>
      К сожалению, победителей в этом розыгрыше нет.
    </div>
  `;
  
  $("#winners-section").style.display = 'none';
  $("#no-winners").style.display = 'block';
  
  if (data.user?.ticket_code) {
    $("#user-ticket").style.display = 'block';
    $("#ticket-code").textContent = data.user.ticket_code;
  }
}

// Функция отображения результатов
function displayResults(data) {
  // Скрываем экран загрузки, показываем экран результатов
  hide("#screen-loading");
  show("#screen-results");
  
  // Заполняем информацию о розыгрыше
  $("#giveaway-title").textContent = data.giveaway.title;
  $("#giveaway-description").textContent = data.giveaway.description || "Описание отсутствует";
  $("#participants-count").textContent = data.giveaway.participants_count;
  $("#winners-count").textContent = data.giveaway.winners_count;
  
  // Отображаем статус пользователя
  const userStatusElement = $("#user-status");
  const winnerStatusElement = $("#winner-status");
  
  if (data.user.ticket_code) {
    $("#user-ticket").style.display = 'block';
    $("#ticket-code").textContent = data.user.ticket_code;
  }
  
  if (data.user.is_winner) {
    winnerStatusElement.innerHTML = `
      <div class="status-message status-winner">
        🎉 Поздравляем! Вы победитель! 🎉<br>
        Ваше место: ${data.user.winner_rank}
      </div>
    `;
  } else if (data.user.ticket_code) {
    winnerStatusElement.innerHTML = `
      <div class="status-message status-participant">
        Спасибо за участие! К сожалению, вы не стали победителем в этом розыгрыше.
      </div>
    `;
  } else {
    winnerStatusElement.innerHTML = `
      <div class="status-message status-participant">
        Вы не участвовали в этом розыгрыше.
      </div>
    `;
  }
  
  // Отображаем список победителей
  const winnersListElement = $("#winners-list");
  winnersListElement.innerHTML = "";
  
  if (data.winners && data.winners.length > 0) {
    data.winners.forEach(winner => {
      const winnerElement = document.createElement("div");
      winnerElement.className = `winner-item ${winner.is_current_user ? 'current-user' : ''}`;
      
      winnerElement.innerHTML = `
        <div class="winner-rank">${winner.rank}</div>
        <div class="winner-info">
          <div class="winner-ticket">${winner.ticket_code}</div>
        </div>
        ${winner.is_current_user ? '<div class="winner-badge">Вы</div>' : ''}
      `;
      
      winnersListElement.appendChild(winnerElement);
    });
    
    $("#winners-section").style.display = 'block';
    $("#no-winners").style.display = 'none';
  } else {
    $("#winners-section").style.display = 'none';
    $("#no-winners").style.display = 'block';
  }
}

// Функция показа ошибки
function showError(message) {
  hide("#screen-loading");
  hide("#screen-results");
  show("#screen-error");
  $("#error-message").textContent = message;
}
