// AUTO-V1 — единый поток: проверка -> выдача билета
console.log("[PrizeMe][AUTO-V1] app.js start");

const tg = window.Telegram?.WebApp || {};
tg.expand?.();
tg.enableClosingConfirmation?.(false);

const $ = (q) => document.querySelector(q);
const show = (sel) => $(sel)?.classList.remove("hide");
const hide = (sel) => $(sel)?.classList.add("hide");

// читаем gid из start_param (или из URL ?tgWebAppStartParam=)
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

// универсальный вызов API c json
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

// Функция для обновления счетчика времени ← ДОБАВЬ ЭТУ ФУНКЦИЮ
function updateCountdown(endAtUtc) {
    try {
        const endTime = new Date(endAtUtc + 'Z'); // Добавляем Z для UTC
        const now = new Date();
        const timeLeft = endTime - now;

        if (timeLeft <= 0) {
            $("#countdown").textContent = "Розыгрыш завершен";
            return;
        }

        // Рассчитываем дни, часы, минуты, секунды
        const days = Math.floor(timeLeft / (1000 * 60 * 60 * 24));
        const hours = Math.floor((timeLeft % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((timeLeft % (1000 * 60)) / 1000);

        // Обновляем отображение
        $("#countdown").textContent = `${days} дн., ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

        // Обновляем каждую секунду
        setTimeout(() => updateCountdown(endAtUtc), 1000);
        
    } catch (err) {
        console.error("[COUNTDOWN] Error:", err);
        $("#countdown").textContent = "Ошибка расчета времени";
    }
}

async function checkFlow() {
  hide("#screen-ok"); hide("#screen-need"); hide("#screen-already"); show("#screen-loading");

  try {
    const gid = getStartParam();
    if (!gid) throw new Error("Empty start_param (gid)");

    const init_data = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || "";
    if (!init_data) throw new Error("No initData");

    console.log("[DEBUG] Starting check with gid:", gid);

    // 1) Проверяем условия
    const check = await api("/api/check", { gid, init_data });
    console.log("[DEBUG] Check response:", check);

    if (check.ok && check.done) {
      console.log("[DEBUG] Conditions met");
      
      if (check.ticket) {
        if (check.is_new_ticket) {
          // НОВЫЙ билет - показываем экран успеха
          console.log("[DEBUG] Showing NEW ticket screen");
          $("#ticket").textContent = check.ticket;
          
          // Обновляем счетчик времени если есть данные ← ДОБАВЬ ЭТО
          if (check.end_at_utc) {
            updateCountdown(check.end_at_utc);
          }
          
          hide("#screen-loading"); 
          show("#screen-ok");
        } else {
          // СУЩЕСТВУЮЩИЙ билет - показываем экран "Уже участвуете"
          console.log("[DEBUG] Showing EXISTING ticket screen");
          $("#already-ticket").textContent = check.ticket;
          
          // Обновляем счетчик времени если есть данные ← ДОБАВЬ ЭТО
          if (check.end_at_utc) {
            updateCountdown(check.end_at_utc);
          }
          
          hide("#screen-loading"); 
          show("#screen-already");
        }
      } else {
        // Нет билета - получаем новый через claim
        console.log("[DEBUG] No ticket, calling claim");
        const claim = await api("/api/claim", { gid, init_data });
        console.log("[DEBUG] Claim response:", claim);
        
        if (claim.ok && claim.ticket) {
          $("#ticket").textContent = claim.ticket;
          
          // Обновляем счетчик времени если есть данные ← ДОБАВЬ ЭТО
          if (claim.end_at_utc) {
            updateCountdown(claim.end_at_utc);
          }
          
          hide("#screen-loading"); 
          show("#screen-ok");
        } else {
          throw new Error("Не удалось получить билет");
        }
      }
      return;
    }

    // 2) Нужно подписаться
    console.log("[DEBUG] Need subscription:", check.need);
    const ul = $("#need-channels");
    ul.innerHTML = "";
    
    if (check.need && check.need.length > 0) {
      check.need.forEach((ch) => {
        const title = ch.title || ch.username || "Канал";
        const url = ch.url || (ch.username ? `https://t.me/${ch.username}` : "#");
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = url; 
        a.target = "_blank"; 
        a.textContent = title;
        a.className = "channel-link";
        
        a.addEventListener("click", (e) => {
          try {
            if (Telegram?.WebApp?.openTelegramLink) { 
              e.preventDefault(); 
              Telegram.WebApp.openTelegramLink(url); 
            }
          } catch (err) {
            console.log("[DEBUG] Open link error:", err);
          }
        });
        
        li.appendChild(a);
        ul.appendChild(li);
      });
    } else {
      ul.innerHTML = "<li>Все условия выполнены, но билет не выдан. Нажмите «Проверить подписку».</li>";
    }

    $("#btn-recheck").onclick = () => {
      console.log("[DEBUG] Manual recheck triggered");
      checkFlow();
    };
    
    hide("#screen-loading"); 
    show("#screen-need");

  } catch (err) {
    console.error("[PrizeMe] checkFlow error:", err);
    $("#need-channels").innerHTML = `<li>Ошибка: ${err.message}. Нажмите «Проверить подписку».</li>`;
    $("#btn-recheck").onclick = () => {
      console.log("[DEBUG] Error recheck triggered");
      checkFlow();
    };
    hide("#screen-loading"); 
    show("#screen-need");
  }
}

// запускаем поток
document.addEventListener("DOMContentLoaded", checkFlow);

// если вернулись из Telegram-канала назад — автоматом перепроверим
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !$("#screen-need")?.classList.contains("hide")) {
    checkFlow();
  }
});