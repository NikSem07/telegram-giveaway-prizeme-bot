// webapp/pages/creator/giveaways/giveaway_card_creator.js
import giveawayCardCreatorTemplate from './giveaway_card_creator.template.js';

function getInitData() {
  return sessionStorage.getItem('prizeme_init_data') || window.Telegram?.WebApp?.initData || '';
}

function formatEndDate(endAtUtc) {
  if (!endAtUtc) return '—';
  const d = new Date(endAtUtc);
  if (Number.isNaN(d.getTime())) return '—';
  const date = d.toLocaleDateString('ru-RU');
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return `${date} ${time}`;
}

async function loadCreatorGiveawayDetails(giveawayId) {
  const init_data = getInitData();
  if (!init_data) throw new Error('no_init_data');

  const r = await fetch('/api/creator_giveaway_details', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data, giveaway_id: giveawayId }),
  });

  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.ok) throw new Error(data?.reason || 'server_error');
  return data;
}

function renderMedia(container, media) {
  container.innerHTML = '';

  if (!media?.url) {
    container.innerHTML = `<div class="creator-giveaway-card-media-empty">Нет медиа</div>`;
    return;
  }

  if ((media.type || '').toLowerCase() === 'video') {
    container.innerHTML = `
      <video class="creator-giveaway-card-media-el" controls playsinline>
        <source src="${media.url}">
      </video>
    `;
    return;
  }

  container.innerHTML = `<img class="creator-giveaway-card-media-el" src="${media.url}" alt="">`;
}

function renderChannels(container, channels) {
  container.innerHTML = (channels || []).map(ch => {
    const avatar = ch.avatar_url || '/miniapp-static/uploads/avatars/default_channel.png';
    const title = ch.title || ch.username || 'Канал';

    return `
      <div class="creator-giveaway-card-channel">
        <div class="creator-giveaway-card-channel-avatar">
          <img src="${avatar}" alt="">
        </div>
        <div class="creator-giveaway-card-channel-title">${title}</div>
      </div>
    `;
  }).join('');
}

function showTelegramBackButton() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.BackButton) return;

  tg.BackButton.show();
  tg.BackButton.onClick(() => {
    window.location.hash = '#/creator/giveaways';
  });
}

function hideTelegramBackButton() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.BackButton) return;
  tg.BackButton.hide();
}

function renderGiveawayCardCreatorPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = giveawayCardCreatorTemplate();

  const giveawayId = sessionStorage.getItem('prizeme_creator_giveaway_id');
  if (!giveawayId) return;

  showTelegramBackButton();

  const titleEl = main.querySelector('#cgcc-title');
  const descEl = main.querySelector('#cgcc-description');
  const endEl = main.querySelector('#cgcc-end');
  const mediaEl = main.querySelector('#cgcc-media');
  const channelsEl = main.querySelector('#cgcc-channels');

  // loading state
  titleEl.textContent = 'Загрузка...';
  descEl.textContent = '';
  endEl.textContent = '';

  loadCreatorGiveawayDetails(giveawayId)
    .then((data) => {
      titleEl.textContent = data.title || '—';
      descEl.textContent = data.description || '—';
      endEl.textContent = formatEndDate(data.end_at_utc);

      renderMedia(mediaEl, data.media);
      renderChannels(channelsEl, data.channels);
    })
    .catch(() => {
      titleEl.textContent = 'Ошибка загрузки';
    });

  // пока заглушка редактирования
  const editBtn = main.querySelector('#cgcc-edit');
  editBtn.addEventListener('click', () => {});
}

export { renderGiveawayCardCreatorPage, hideTelegramBackButton };
