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
  try {
    const p = tg.initDataUnsafe?.start_param;
    if (p) return p;
  } catch {}
  try {
    const url = new URL(location.href);
    return url.searchParams.get("tgWebAppStartParam");
  } catch { return null; }
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

// Основной поток проверки
async function checkFlow() {
  try {
    const gid = getStartParam();
    if (!gid) throw new Error("Empty start_param (gid)");

    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) throw new Error("No initData");

    console.log("[MULTI-PAGE] Starting check with gid:", gid);

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
  // Главная страница сразу запускает проверку и редиректит на loading
  const gid = getStartParam();
  if (gid) {
    sessionStorage.setItem('prizeme_gid', gid);
    window.location.href = '/miniapp/loading';
  } else {
    document.getElementById('main-content').innerHTML = `
      <div class="card">
        <h1>Ошибка</h1>
        <p>Не удалось определить розыгрыш. Проверьте ссылку.</p>
      </div>
    `;
  }
}

// Инициализация для экрана загрузки
function initializeLoadingPage() {
  console.log("[MULTI-PAGE] Initializing loading page");
  // Экран загрузки сразу запускает проверку
  setTimeout(() => {
    checkFlow();
  }, 500);
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
    default:
      // Для неизвестных путей - редирект на главную
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