// webapp/pages/creator/giveaways/giveaway_card_creator.js
import giveawayCardCreatorTemplate from './giveaway_card_creator.template.js';

import Router from '../../../shared/router.js';

const STORAGE_TAB_KEY = 'prizeme_creator_giveaways_tab';

function backToGiveaways() {
  // Вкладка уже сохранена в sessionStorage на экране списка.
  Router.navigate('giveaways');
}

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

  const type = (media.type || '').toLowerCase();

  if (type === 'video') {
    container.innerHTML = `
      <div class="creator-giveaway-card-media-wrap">
        <video class="creator-giveaway-card-media-el" playsinline preload="metadata"></video>
        <button class="creator-giveaway-card-play" type="button" aria-label="Play"></button>
      </div>
    `;

    const video = container.querySelector('video');
    const playBtn = container.querySelector('.creator-giveaway-card-play');

    // source
    video.src = media.url;

    // fade-in на данные
    video.addEventListener('loadeddata', () => {
      video.classList.add('is-loaded');
    }, { once: true });

    const hideOverlay = () => playBtn.classList.add('is-hidden');
    const showOverlay = () => playBtn.classList.remove('is-hidden');

    playBtn.addEventListener('click', async () => {
      try {
        // чтобы после старта пользователь мог паузить/скроллить таймлайн
        video.controls = true;
        await video.play();
        hideOverlay();
      } catch (e) {
        // если autoplay policy — оставим overlay
        showOverlay();
      }
    });

    video.addEventListener('play', hideOverlay);
    video.addEventListener('pause', () => {
      // если пользователь поставил на паузу — вернём overlay
      if (!video.ended) showOverlay();
    });
    video.addEventListener('ended', showOverlay);

    return;
  }

  // image
  container.innerHTML = `<img class="creator-giveaway-card-media-el" src="${media.url}" alt="">`;
  const img = container.querySelector('img');

  img.addEventListener('load', () => {
    img.classList.add('is-loaded');
  }, { once: true });

  img.addEventListener('error', () => {
    container.innerHTML = `<div class="creator-giveaway-card-media-empty">Не удалось загрузить медиа</div>`;
  }, { once: true });
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

  // гарантируем единственный хендлер
  try { tg.BackButton.offClick(backToGiveaways); } catch (e) {}
  tg.BackButton.onClick(backToGiveaways);
  tg.BackButton.show();
}

function hideTelegramBackButton() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.BackButton) return;

  try { tg.BackButton.offClick(backToGiveaways); } catch (e) {}
  tg.BackButton.hide();
}

function renderGiveawayCardCreatorPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = giveawayCardCreatorTemplate();

  document.body.classList.add('page-creator-giveaway-card');

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

  const editBtn = main.querySelector('#cgcc-edit');
  editBtn.addEventListener('click', () => {
    const giveawayId = sessionStorage.getItem('prizeme_creator_giveaway_id');
    if (!giveawayId) return;
    showEditPopup(giveawayId);
  });
}

async function getBotUsername() {
  const r = await fetch('/api/bot_username');
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.ok || !data.username) throw new Error('no_bot_username');
  return data.username;
}

function getReturnTabKey() {
  return sessionStorage.getItem(STORAGE_TAB_KEY) || 'active';
}

function buildEditStartParam(giveawayId) {
  const tab = getReturnTabKey(); // active / draft / completed
  const botTab = (tab === 'completed') ? 'finished' : tab; // маппинг в статусы бота/БД
  return `edit_creator_${botTab}_${giveawayId}`;
}

async function goEditInBot(giveawayId) {
  const tg = window.Telegram?.WebApp;
  const username = await getBotUsername();
  const startParam = buildEditStartParam(giveawayId);

  const url = `https://t.me/${username}?start=${encodeURIComponent(startParam)}`;

  // Открываем бота и закрываем миниапп
  if (tg?.openTelegramLink) tg.openTelegramLink(url);
  else window.location.href = url;

  if (tg?.close) tg.close();
}

function showEditPopup(giveawayId) {
  const tg = window.Telegram?.WebApp;

  const message = 'Для редактирования розыгрыша Вы будете перемещены в чат с ботом! Продолжить?';

  if (tg?.showPopup) {
    tg.showPopup(
      {
        title: 'Редактирование',
        message,
        buttons: [
          { id: 'yes', type: 'default', text: 'Да' },
          { id: 'no', type: 'destructive', text: 'Отмена' }
        ],
      },
      async (buttonId) => {
        if (buttonId !== 'yes') return;
        try {
          await goEditInBot(giveawayId);
        } catch (e) {
          // fallback: можно позже заменить на аккуратный alert/toast
          if (tg?.showAlert) tg.showAlert('Не удалось открыть бота. Попробуйте позже.');
        }
      }
    );
    return;
  }

  // Fallback для браузера
  if (window.confirm(message)) {
    goEditInBot(giveawayId).catch(() => {});
  }
}

export { renderGiveawayCardCreatorPage, hideTelegramBackButton };
