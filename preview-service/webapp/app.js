// AUTO-V1 build — автопроверка подписки и выдача билета
console.log("[PrizeMe][AUTO-V1] app.js loaded");

const tg = window.Telegram?.WebApp || {};
tg.expand?.();
tg.enableClosingConfirmation?.(false);

const $ = (q) => document.querySelector(q);
const show = (sel) => $(sel).classList.remove("hide");
const hide = (sel) => $(sel).classList.add("hide");

function getStartParam() {
  try {
    const p = tg.initDataUnsafe?.start_param;
    if (p) return p;
  } catch {}
  const url = new URL(location.href);
  return url.searchParams.get("tgWebAppStartParam");
}

async function callCheck(gid) {
  const payload = { gid, init_data: tg.initData || "" };
  const resp = await fetch("/api/check-join", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload),
    credentials: "include",
  });
  if (!resp.ok) throw new Error("HTTP "+resp.status+" "+(await resp.text().catch(()=>resp.statusText)));
  return resp.json();
}

function renderNeed(channels) {
  const ul = $("#need-list");
  ul.innerHTML = "";
  (channels || []).forEach((ch) => {
    const li = document.createElement("li");
    li.className = "item";
    const url = ch.url || (ch.username ? `https://t.me/${ch.username}` : "#");
    li.innerHTML = `<div><strong>${ch.title || "Канал"}</strong></div>
                    <a class="link" href="${url}" target="_blank" rel="noopener">Открыть</a>`;
    li.querySelector("a").addEventListener("click", (e) => {
      try { if (tg.openTelegramLink) { e.preventDefault(); tg.openTelegramLink(url); } } catch {}
    });
    ul.appendChild(li);
  });
}

async function checkFlow() {
  hide("#screen-ok"); hide("#screen-need"); hide("#screen-fail");
  show("#screen-loading");
  try {
    const gid = getStartParam();
    if (!gid) throw new Error("start_param is empty");

    const data = await callCheck(gid);
    if (data.ok) {
      $("#ticket").textContent = data.ticket || "—";
      hide("#screen-loading"); show("#screen-ok");
      tg.MainButton?.hide?.();
    } else {
      renderNeed(data.need || []);
      hide("#screen-loading"); show("#screen-need");
    }
  } catch (err) {
    console.error("[PrizeMe] check error:", err);
    hide("#screen-loading"); show("#screen-fail");
  }
}

$("#btn-retry")?.addEventListener("click", checkFlow);
$("#btn-retry-2")?.addEventListener("click", checkFlow);
$("#btn-done")?.addEventListener("click", () => { try{ tg.close?.(); }catch{} });

document.addEventListener("DOMContentLoaded", checkFlow);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && $("#screen-need") && !$("#screen-need").classList.contains("hide")) {
    checkFlow();
  }
});
