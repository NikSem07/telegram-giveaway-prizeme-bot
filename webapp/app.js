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
  hide("#screen-ok"); hide("#screen-need"); show("#screen-loading");

  try {
    const gid = getStartParam(); // как у тебя: берём из startapp (gid)
    if (!gid) throw new Error("start_param is empty");

    // Telegram WebApp init data
    const initDataUnsafe = tg.initDataUnsafe || {};
    const user = initDataUnsafe.user || {};
    const user_id = user.id;
    const username = user.username || null;

    const resp = await fetch("/api/check", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ gid, user_id, username })
    });
    const data = await resp.json();

    if (!data || resp.status >= 400) throw new Error("check_failed");

    // осталось времени
    const endsAt = data.ends_at ? new Date(data.ends_at * 1000) : null;

    if (data.ok) {
      // уже участвует? покажем билет сразу
      if (data.ticket) {
        $("#ticket").textContent = data.ticket;
      } else {
        // запросим выдачу билета
        const claimResp = await fetch("/api/claim", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ gid, user_id })
        });
        const claim = await claimResp.json();
        if (claim && claim.ok && claim.ticket) {
          $("#ticket").textContent = claim.ticket;
        } else {
          $("#ticket").textContent = "—";
        }
      }
      hide("#screen-loading"); show("#screen-ok");
      tg.MainButton?.hide();
    } else {
      // нужно подписаться
      const ul = $("#need-channels");
      ul.innerHTML = "";
      (data.need || []).forEach(ch => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = ch.link || (ch.username ? `https://t.me/${ch.username}` : "#");
        a.target = "_blank";
        a.textContent = ch.title || ch.username || ch.id;
        li.appendChild(a);
        ul.appendChild(li);
      });

      // кнопка «Проверить подписку»
      const btn = $("#btn-recheck");
      btn.onclick = () => checkFlow();

      hide("#screen-loading"); show("#screen-need");
    }
  } catch (e) {
    console.error(e);
    hide("#screen-loading"); show("#screen-need");
    $("#need-channels").innerHTML = "<li>Ошибка проверки. Нажмите «Проверить подписку».</li>";
    $("#btn-recheck").onclick = () => checkFlow();
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
