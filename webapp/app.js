// MULTI-PAGE-V1 — многостраничная версия Mini App
console.log("[PrizeMe][MULTI-PAGE-V1] app.js start");

const tg = window.Telegram?.WebApp || {};
tg.expand?.();
tg.enableClosingConfirmation?.(false);

const $ = (q) => document.querySelector(q);
const show = (sel) => $(sel)?.classList.remove("hide");
const hide = (sel) => $(sel)?.classList.add("hide");

// Получаем start_param из URL или initData
function getStartParam() {
  console.log('🎯 [getStartParam] Starting parameter search...');
  
  try {
    // ПРИОРИТЕТ 1: Пробуем получить из URL параметра (gid)
    const url = new URL(location.href);
    const urlGid = url.searchParams.get("gid");
    if (urlGid) {
      console.log('🎯 [getStartParam] ✅ Got gid from URL:', urlGid);
      return urlGid;
    }
  } catch (e) {
    console.log('[getStartParam] URL parse error:', e);
  }

  try {
    // ПРИОРИТЕТ 2: Пробуем получить из sessionStorage
    const sessionGid = sessionStorage.getItem('prizeme_gid');
    if (sessionGid) {
      console.log('🎯 [getStartParam] ✅ Got gid from sessionStorage:', sessionGid);
      return sessionGid;
    }
  } catch (e) {
    console.log('[getStartParam] sessionStorage error:', e);
  }

  try {
    // ПРИОРИТЕТ 3: Пробуем получить из URL параметра tgWebAppStartParam
    const url = new URL(location.href);
    const urlParam = url.searchParams.get("tgWebAppStartParam");
    if (urlParam && urlParam !== 'demo') {
      console.log('🎯 [getStartParam] ✅ Got tgWebAppStartParam from URL:', urlParam);
      
      // Обработка результатов
      if (urlParam.startsWith('results_')) {
        const gid = urlParam.replace('results_', '');
        sessionStorage.setItem('prizeme_results_gid', gid);
        return gid;
      }
      
      return urlParam;
    }
  } catch (e) {
    console.log('[getStartParam] URL parse error:', e);
  }

  try {
    // ПРИОРИТЕТ 4: Пробуем получить из initData
    const p = tg.initDataUnsafe?.start_param;
    if (p && p !== 'demo') {
      console.log('🎯 [getStartParam] ✅ Got start_param from initData:', p);
      
      if (p.startsWith('results_')) {
        const gid = p.replace('results_', '');
        sessionStorage.setItem('prizeme_results_gid', gid);
        return gid;
      }
      
      return p;
    }
  } catch (e) {
    console.log('[getStartParam] initData parse error:', e);
  }

  console.log('❌ [getStartParam] No valid start_param found in any source');
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
    const url = new URL(location.href);
    const urlParam = url.searchParams.get("tgWebAppStartParam");
    
    if (urlParam && urlParam.startsWith('results_')) {
      const gid = urlParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] 🎲 Immediately redirecting to results for gid:", gid);
      window.location.href = `/miniapp/results?gid=${gid}`;
      return true;
    }
    
    // Проверяем initData для результатов
    const initParam = tg.initDataUnsafe?.start_param;
    if (initParam && initParam.startsWith('results_')) {
      const gid = initParam.replace('results_', '');
      console.log("[IMMEDIATE-RESULTS] 🎲 Immediately redirecting to results from initData, gid:", gid);
      window.location.href = `/miniapp/results?gid=${gid}`;
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
function updateCountdown(endAtUtc, elementId = 'countdown') {
    try {
        const endTime = new Date(endAtUtc + 'Z');
        const now = new Date();
        const timeLeft = endTime - now;

        const countdownElement = $(`#${elementId}`);
        if (!countdownElement) return;

        if (timeLeft <= 0) {
            countdownElement.textContent = "Розыгрыш завершен";
            return;
        }

        const days = Math.floor(timeLeft / (1000 * 60 * 60 * 24));
        const hours = Math.floor((timeLeft % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((timeLeft % (1000 * 60)) / 1000);

        countdownElement.textContent = `${days} дн., ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

        setTimeout(() => updateCountdown(endAtUtc, elementId), 1000);
        
    } catch (err) {
        console.error("[COUNTDOWN] Error:", err);
        const countdownElement = $(`#${elementId}`);
        if (countdownElement) {
            countdownElement.textContent = "Ошибка расчета времени";
        }
    }
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

    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) throw new Error("No initData");

    console.log("[MULTI-PAGE] Starting check with gid:", gid);

    // 🔄 НОВАЯ ПРОВЕРКА: если розыгрыш завершен - сразу показываем результаты
    const isCompleted = await checkGiveawayCompletion(gid);
    if (isCompleted) {
      console.log("[MULTI-PAGE] Giveaway completed, redirecting to RESULTS screen");
      window.location.href = `/miniapp/results?gid=${gid}`;
      return;
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
          // Сохраняем данные для следующего экрана
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
    // В случае ошибки - показываем экран подписки с сообщением об ошибке
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
  console.log("[MULTI-PAGE] Initializing need subscription page");
  
  const needData = JSON.parse(sessionStorage.getItem('prizeme_need_data') || '[]');
  const error = sessionStorage.getItem('prizeme_error');
  
  const ul = $("#need-channels");
  ul.innerHTML = "";
  
  if (error) {
    ul.innerHTML = `<li class="err">Ошибка: ${error}. Нажмите «Проверить подписку».</li>`;
  } else if (needData && needData.length > 0) {
    needData.forEach((ch) => {
      const title = ch.title || ch.username || "Канал";
      const url = ch.url || (ch.username ? `https://t.me/${ch.username}` : "#");
      const li = document.createElement("li");
      li.className = "item";
      
      const a = document.createElement("a");
      a.href = url; 
      a.target = "_blank"; 
      a.textContent = title;
      a.className = "link";
      
      a.addEventListener("click", (e) => {
        try {
          if (Telegram?.WebApp?.openTelegramLink) { 
            e.preventDefault(); 
            Telegram.WebApp.openTelegramLink(url); 
          }
        } catch (err) {
          console.log("[MULTI-PAGE] Open link error:", err);
        }
      });
      
      li.appendChild(a);
      ul.appendChild(li);
    });
  } else {
    ul.innerHTML = "<li class='item'>Все условия выполнены, но билет не выдан. Нажмите «Проверить подписку».</li>";
  }

  $("#btn-recheck").onclick = () => {
    console.log("[MULTI-PAGE] Manual recheck triggered");
    sessionStorage.removeItem('prizeme_error');
    sessionStorage.removeItem('prizeme_need_data');
    window.location.href = '/miniapp/loading';
  };
}

// Инициализация для экрана "Успех"
function initializeSuccessPage() {
  console.log("[MULTI-PAGE] Initializing success page");
  
  const ticket = sessionStorage.getItem('prizeme_ticket');
  const endAt = sessionStorage.getItem('prizeme_end_at');
  
  if (ticket) {
    $("#ticket").textContent = ticket;
  }
  
  if (endAt) {
    updateCountdown(endAt, 'countdown');
  }
  
  // Очищаем storage после использования
  sessionStorage.removeItem('prizeme_ticket');
  sessionStorage.removeItem('prizeme_end_at');
  sessionStorage.removeItem('prizeme_gid');
  sessionStorage.removeItem('prizeme_init_data');
}

// Инициализация для экрана "Уже участвуете"
function initializeAlreadyPage() {
  console.log("[MULTI-PAGE] Initializing already page");
  
  const ticket = sessionStorage.getItem('prizeme_ticket');
  const endAt = sessionStorage.getItem('prizeme_end_at');
  
  if (ticket) {
    $("#already-ticket").textContent = ticket;
  }
  
  if (endAt) {
    updateCountdown(endAt, 'countdown-already');
  }
  
  // Очищаем storage после использования
  sessionStorage.removeItem('prizeme_ticket');
  sessionStorage.removeItem('prizeme_end_at');
  sessionStorage.removeItem('prizeme_gid');
  sessionStorage.removeItem('prizeme_init_data');
}

// Определяем текущую страницу и инициализируем соответствующую логику
function initializeCurrentPage() {
  const path = window.location.pathname;
  console.log("[MULTI-PAGE] Current path:", path);
  
  // ПРЕЖДЕ всего проверяем немедленный редирект на результаты
  if (checkImmediateResults()) {
    return; // Останавливаем дальнейшее выполнение
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
    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) {
      throw new Error("No initData");
    }
    
    console.log("[RESULTS] Loading results for gid:", gid);
    
    const results = await api("/api/results", { gid, init_data });
    console.log("[RESULTS] Results response:", results);
    
    if (results.ok) {
      displayResults(results);
    } else {
      throw new Error(results.reason || "Failed to load results");
    }
    
  } catch (err) {
    console.error("[RESULTS] Error loading results:", err);
    showError(err.message);
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
