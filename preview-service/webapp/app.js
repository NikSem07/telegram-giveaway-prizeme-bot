const tg = window.Telegram?.WebApp;
try { tg?.expand?.(); } catch(_) {}

async function postJSON(url, data){
  const r = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data) });
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : { ok:false, status:r.status };
}
const Q = (id)=>document.getElementById(id);
const show = (id)=>Q(id).classList.remove("hidden");
const hide = (id)=>Q(id).classList.add("hidden");

const initData   = tg?.initData || "";
const startParam = tg?.initDataUnsafe?.start_param || "";
const gid        = Number(startParam) || 0;

async function checkNow(){
  hide("screen-ok"); hide("screen-fail"); show("screen-loading");
  try{
    const resp = await postJSON("/api/check-join", { gid, init_data: initData });
    if (resp?.ok){
      Q("ticket").textContent = resp.ticket || "— — — — — —";
      hide("screen-loading"); show("screen-ok");
    }else{
      const need = Array.isArray(resp?.need) ? resp.need : [];
      const ul = Q("need-list"); ul.innerHTML = "";
      need.forEach(ch => {
        const url = ch.url || (ch.username ? ("https://t.me/"+ch.username) : "#");
        const li = document.createElement("li"); li.className = "item";
        li.innerHTML = `
          <div class="row">
            <div><strong>${ch.title || "Канал"}</strong><div class="muted">${ch.username ? "@"+ch.username : ""}</div></div>
            <a class="link" href="${url}" target="_blank" rel="noopener">Открыть</a>
          </div>`;
        li.querySelector("a").addEventListener("click", (e) => {
          e.preventDefault();
          const link = e.currentTarget.getAttribute("href");
          if (tg?.openTelegramLink){ tg.openTelegramLink(link); } else { window.open(link, "_blank"); }
        });
        ul.appendChild(li);
      });
      hide("screen-loading"); show("screen-fail");
    }
  }catch(e){
    const ul = Q("need-list");
    ul.innerHTML = `<li class="item err">Не удалось связаться с сервером. Проверьте интернет и попробуйте ещё раз.</li>`;
    hide("screen-loading"); show("screen-fail");
  }
}

document.addEventListener("DOMContentLoaded", checkNow);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkNow(); });

Q("btn-retry").onclick = checkNow;
Q("btn-done").onclick  = () => { try{ tg?.close(); } catch(_){} };
