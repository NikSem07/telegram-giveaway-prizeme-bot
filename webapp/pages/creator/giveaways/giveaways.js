// webapp/pages/creator/giveaways/giveaways.js
import creatorGiveawaysTemplate from './giveaways.template.js';

const TAB_TO_API_STATUS = {
  active: 'active',       // Запущенные
  draft: 'draft',         // Незапущенные (все кроме active/completed/finished)
  completed: 'completed', // Завершенные
};

function getInitData() {
  // 1) то, что мы сохраняем в sessionStorage при входе через /miniapp/ (у тебя так уже сделано)
  const fromSession = sessionStorage.getItem('prizeme_init_data');
  if (fromSession) return fromSession;

  // 2) фолбэк - Telegram WebApp
  const tg = window.Telegram?.WebApp;
  return tg?.initData || '';
}

function formatEndDate(endAtUtc) {
  if (!endAtUtc) return 'Дата окончания: —';
  const d = new Date(endAtUtc);
  if (Number.isNaN(d.getTime())) return 'Дата окончания: —';
  // Формат можно поменять, но сейчас строго "дата окончания" (без таймера)
  const date = d.toLocaleDateString('ru-RU');
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return `Дата окончания: ${date} ${time}`;
}

function renderCards(listEl, items) {
  listEl.innerHTML = items.map(item => {
    const avatarUrl = item.first_channel_avatar_url || '/miniapp-static/uploads/avatars/default_channel.png';
    const channels = Array.isArray(item.channels) ? item.channels.filter(Boolean).join(', ') : '';
    const title = item.title || 'Без названия';
    const endText = formatEndDate(item.end_at_utc);

    return `
    <article class="creator-giveaways-card" data-giveaway-id="${item.id}" role="button" tabindex="0">
        <div class="creator-giveaways-card__avatar">
        <img src="${avatarUrl}" alt="">
        </div>

        <div class="creator-giveaways-card__body">
        <div class="creator-giveaways-card__channels">${channels || 'Каналы не указаны'}</div>
        <div class="creator-giveaways-card__title">${title}</div>
        <div class="creator-giveaways-card__end">${endText}</div>
        </div>

        <div class="creator-giveaways-card__arrow" aria-hidden="true">
        <img src="/miniapp-static/assets/icons/arrow-icon.svg" alt="">
        </div>
    </article>
    `;
  }).join('');
}

async function loadCreatorGiveaways(status) {
  const init_data = getInitData();
  if (!init_data) {
    return { ok: false, total: 0, items: [], reason: 'no_init_data' };
  }

  const r = await fetch('/api/creator_giveaways', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data, status }),
  });

  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.ok) {
    return { ok: false, total: 0, items: [], reason: data?.reason || 'server_error' };
  }

  return data;
}

function initTabs(root) {
  const tabs = Array.from(root.querySelectorAll('.creator-giveaways__tab'));
  const totalEl = root.querySelector('#creator-giveaways-total');
  const listEl = root.querySelector('#creator-giveaways-list');

  const setActiveTab = (tabKey) => {
    tabs.forEach(btn => btn.classList.toggle('is-active', btn.dataset.tab === tabKey));
  };

  const renderState = async (tabKey) => {
    const apiStatus = TAB_TO_API_STATUS[tabKey] || 'active';
    setActiveTab(tabKey);

    totalEl.textContent = 'Всего: ...';
    listEl.innerHTML = '';

    const resp = await loadCreatorGiveaways(apiStatus);
    const items = Array.isArray(resp.items) ? resp.items : [];
    totalEl.textContent = `Всего: ${resp.total ?? items.length}`;
    renderCards(listEl, items);
  };

  // Клики по табам
  tabs.forEach(btn => {
    btn.addEventListener('click', () => renderState(btn.dataset.tab));
  });

  // стартуем с "Запущенные"
  renderState('active');
}

function renderGiveawaysPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = creatorGiveawaysTemplate();

  const root = main.querySelector('.creator-giveaways');
  if (!root) return;

  initTabs(root);
}

export { renderGiveawaysPage };
