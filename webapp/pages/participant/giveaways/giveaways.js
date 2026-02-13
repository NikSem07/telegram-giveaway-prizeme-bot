import giveawaysTemplate from './giveaways.template.js';
import Router from '../../../shared/router.js';

const TAB_TO_API_STATUS = {
  active: 'active',
  finished: 'finished',
  cancelled: 'cancelled',
};

const STORAGE_TAB_KEY = 'prizeme_participant_giveaways_tab';
const STORAGE_SCROLL_KEY = 'prizeme_participant_giveaways_scroll_y';

function getInitData() {
  const fromSession = sessionStorage.getItem('prizeme_init_data');
  if (fromSession) return fromSession;

  const tg = window.Telegram?.WebApp;
  return tg?.initData || '';
}

function formatEndDate(endAtUtc) {
  if (!endAtUtc) return 'Дата окончания: —';
  const d = new Date(endAtUtc);
  if (Number.isNaN(d.getTime())) return 'Дата окончания: —';
  const date = d.toLocaleDateString('ru-RU');
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return `Дата окончания: ${date} ${time}`;
}

function setActiveTabUI(tab) {
  const tabs = document.querySelectorAll('.participant-giveaways__tab');
  tabs.forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle('is-active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
}

function renderState(text) {
  const stateEl = document.getElementById('participant-giveaways-state');
  if (!stateEl) return;
  stateEl.innerHTML = text ? `<div class="participant-giveaways__hint">${text}</div>` : '';
}

function renderCount(total) {
  const el = document.getElementById('participant-giveaways-count');
  if (!el) return;
  el.textContent = `Всего: ${Number.isFinite(total) ? total : '—'}`;
}

function renderCards(listEl, items) {
  listEl.innerHTML = items.map(item => {
    const avatarUrl = item.first_channel_avatar_url || '/miniapp-static/uploads/avatars/default_channel.png';
    const channels = Array.isArray(item.channels) ? item.channels.filter(Boolean).join(', ') : '';
    const title = item.title || 'Без названия';
    const endText = formatEndDate(item.end_at_utc);

    return `
      <article class="participant-giveaways-card" data-giveaway-id="${item.id}" role="button" tabindex="0">
        <div class="participant-giveaways-card__left">
          <div class="participant-giveaways-card__avatar">
            <img src="${avatarUrl}" alt="" loading="lazy" />
          </div>
        </div>

        <div class="participant-giveaways-card__body">
          <div class="participant-giveaways-card__channels">${channels || '—'}</div>
          <div class="participant-giveaways-card__title">${title}</div>
          <div class="participant-giveaways-card__meta">${endText}</div>
        </div>

        <div class="participant-giveaways-card__right">
          <div class="participant-giveaways-card__arrow">
            <img src="/miniapp-static/assets/icons/arrow-icon.svg" alt="" />
          </div>
        </div>
      </article>
    `;
  }).join('');
}

async function fetchGiveaways(tab) {
  const init_data = getInitData();
  const status = TAB_TO_API_STATUS[tab] || 'active';

  const resp = await fetch('/api/participant_giveaways', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data, status })
  });

  const data = await resp.json().catch(() => null);
  if (!resp.ok || !data || !data.ok) {
    const reason = data?.reason || `http_${resp.status}`;
    throw new Error(reason);
  }

  return data;
}

function bindCardNavigation(listEl, tab) {
  const go = (gid) => {
    // active -> participant giveaway card
    if (tab === 'active') {
        sessionStorage.setItem('prizeme_participant_giveaway_id', String(gid));
        sessionStorage.setItem('prizeme_participant_card_mode', 'active');
        Router.navigate('giveaway_card_participant');
        return;
    }

    // finished -> participant giveaway card (как active)
    if (tab === 'finished') {
        sessionStorage.setItem('prizeme_participant_giveaway_id', String(gid));
        sessionStorage.setItem('prizeme_participant_card_mode', 'finished');
        Router.navigate('giveaway_card_participant');
        return;
    }

    // cancelled -> пока не ведём (логику/экран сделаем позже)
    // можно оставить no-op, чтобы не ломать UX
  };

  listEl.querySelectorAll('.participant-giveaways-card').forEach(card => {
    const gid = Number(card.dataset.giveawayId);
    if (!Number.isFinite(gid)) return;

    card.addEventListener('click', () => go(gid));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        go(gid);
      }
    });
  });
}

async function loadTab(tab) {
  const listEl = document.getElementById('participant-giveaways-list');
  if (!listEl) return;

  setActiveTabUI(tab);
  renderCount(NaN);
  renderState('Загрузка…');
  listEl.innerHTML = '';

  // сохраняем выбранную вкладку
  localStorage.setItem(STORAGE_TAB_KEY, tab);

  try {
    const data = await fetchGiveaways(tab);
    const items = Array.isArray(data.items) ? data.items : [];

    renderCount(items.length);

    if (!items.length) {
      const emptyText =
        tab === 'active'
          ? 'Пока нет активных розыгрышей, в которых вы участвуете.'
          : tab === 'finished'
            ? 'Пока нет завершённых розыгрышей, в которых вы участвовали.'
            : 'Пока нет отменённых розыгрышей, в которых вы участвовали.';

      renderState(emptyText);
      return;
    }

    renderState('');
    renderCards(listEl, items);
    bindCardNavigation(listEl, tab);

  } catch (e) {
    renderState('Не удалось загрузить список. Попробуйте ещё раз.');
    console.error('[participant giveaways] load error:', e);
  }
}

function bindTabs() {
  const tabs = document.querySelectorAll('.participant-giveaways__tab');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab || 'active';
      loadTab(tab);
    });
  });
}

function restoreScroll() {
  const y = Number(sessionStorage.getItem(STORAGE_SCROLL_KEY));
  if (Number.isFinite(y) && y > 0) {
    window.scrollTo(0, y);
  }
}

function bindScrollSaver() {
  window.addEventListener('scroll', () => {
    sessionStorage.setItem(STORAGE_SCROLL_KEY, String(window.scrollY || 0));
  }, { passive: true });
}

function renderGiveawaysPage() {
  const tg = window.Telegram?.WebApp;
  if (tg?.BackButton) tg.BackButton.hide();
  document.body.classList.remove('page-participant-giveaway-card');
  const main = document.getElementById('main-content');
  if (!main) return;

  const context = { timestamp: new Date().toISOString() };
  main.innerHTML = giveawaysTemplate(context);

  bindTabs();
  bindScrollSaver();

  const savedTab = localStorage.getItem(STORAGE_TAB_KEY);
  const initialTab = TAB_TO_API_STATUS[savedTab] ? savedTab : 'active';

  loadTab(initialTab).then(() => {
    restoreScroll();
  });
}

export { renderGiveawaysPage };
