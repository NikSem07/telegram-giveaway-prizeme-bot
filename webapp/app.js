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
          hide("#screen-loading"); 
          show("#screen-ok");
        } else {
          // СУЩЕСТВУЮЩИЙ билет - показываем экран "Уже участвуете"
          console.log("[DEBUG] Showing EXISTING ticket screen");
          $("#already-ticket").textContent = check.ticket;
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

// Функция для расчета оставшегося времени
function calculateTimeLeft(createdAt, endAt) {
    const now = new Date();
    const created = new Date(createdAt);
    const end = new Date(endAt);
    
    // Время окончания = время создания + (разница между окончанием и созданием)
    const actualEndTime = new Date(created.getTime() + (end.getTime() - created.getTime()));
    
    return Math.max(0, actualEndTime - now);
}