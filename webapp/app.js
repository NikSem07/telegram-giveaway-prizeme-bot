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
  hide("#screen-ok"); hide("#screen-need"); show("#screen-loading");

  try {
    const gid = getStartParam();
    if (!gid) throw new Error("Empty start_param (gid)");

    const user = tg.initDataUnsafe?.user || {};
    const user_id = user.id;
    const username = user.username || null;
    if (!user_id) throw new Error("No user_id in initDataUnsafe");

    // 1) Проверка подписки/статуса
    const check = await api("/api/check", { gid, user_id, username });

    if (check.ok) {
      // уже участник? покажем билет/затребуем билет
      if (check.ticket) {
        $("#ticket").textContent = check.ticket;
      } else {
        // 2) Если билета нет — запрашиваем выдачу
        const claim = await api("/api/claim", { gid, user_id });
        $("#ticket").textContent = claim.ticket || "—";
      }
      hide("#screen-loading"); show("#screen-ok");
      tg.MainButton?.hide?.();
      return;
    }

    // Нужны подписки — рендерим список и кнопку «Проверить подписку»
    const ul = $("#need-channels");
    ul.innerHTML = "";
    (check.need || []).forEach((ch) => {
      const url = ch.link || (ch.username ? `https://t.me/${ch.username}` : "#");
      const li = document.createElement("li");
      const a  = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.textContent = ch.title || ch.username || ch.id || "Канал";
      a.addEventListener("click", (e) => {
        try { if (tg.openTelegramLink) { e.preventDefault(); tg.openTelegramLink(url); } } catch {}
      });
      li.appendChild(a);
      ul.appendChild(li);
    });

    $("#btn-recheck").onclick = () => checkFlow();
    hide("#screen-loading"); show("#screen-need");
  } catch (err) {
    console.error("[PrizeMe][AUTO-V1] checkFlow error:", err);
    $("#need-channels").innerHTML = "<li>Ошибка проверки. Нажмите «Проверить подписку».</li>";
    $("#btn-recheck").onclick = () => checkFlow();
    hide("#screen-loading"); show("#screen-need");
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
