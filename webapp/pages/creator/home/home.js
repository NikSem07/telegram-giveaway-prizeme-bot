// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';

// API helper (минимальный, чтобы не зависеть от других модулей)
async function api(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return await res.json();
}

function getInitDataSafe() {
  const tg = window.Telegram?.WebApp;

  let init_data = tg?.initData || '';

  // fallback на sessionStorage как у тебя уже сделано в других местах
  if (!init_data) {
    try {
      const stored = sessionStorage.getItem('prizeme_init_data');
      if (stored) init_data = stored;
    } catch (e) {}
  }

  return init_data || '';
}

function openTelegramLink(url) {
  const tg = window.Telegram?.WebApp;
  try {
    if (tg?.openLink) {
      tg.openLink(url);
      return;
    }
  } catch (e) {}
  window.open(url, '_blank');
}

async function loadCreatorTotalGiveaways() {
  const init_data = getInitDataSafe();
  if (!init_data) return null;

  const data = await api('/api/creator_total_giveaways', { init_data });
  if (!data || !data.ok) return null;

  const n = Number(data.total_giveaways);
  return Number.isFinite(n) ? n : null;
}

export async function renderCreatorHomePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  // 1) Рендерим сразу каркас (чтобы UI мгновенно появился)
  main.innerHTML = creatorHomeTemplate({ totalGiveaways: null });
  attachEventListeners(main);

  // 2) Подгружаем число и обновляем только текст
  try {
    const total = await loadCreatorTotalGiveaways();
    const el = main.querySelector('#creator-total-giveaways');
    if (el && total !== null) el.textContent = String(total);
  } catch (e) {
    // молча: оставим "--"
    console.log('[CreatorHome] total giveaways load failed:', e);
  }
}

function attachEventListeners(container) {
  // Big card: create giveaway (у тебя уже есть window.createGiveaway)
  container.querySelector('[data-creator-action="create"]')?.addEventListener('click', () => {
    window.createGiveaway?.();
  });

  // Donate
  container.querySelector('[data-creator-action="donate"]')?.addEventListener('click', () => {
    openTelegramLink('https://t.me/tribute/app?startapp=dA1o');
  });

  // Subscribe
  container.querySelector('[data-creator-action="subscribe"]')?.addEventListener('click', () => {
    openTelegramLink('https://t.me/tribute/app?startapp=sHOW');
  });
}
