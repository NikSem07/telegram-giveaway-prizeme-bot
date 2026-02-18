// webapp/pages/creator/giveaways/giveaway_card_creator.js
import giveawayCardCreatorTemplate from './giveaway_card_creator.template.js';

import Router from '../../../shared/router.js';

const STORAGE_TAB_KEY = 'prizeme_creator_giveaways_tab';

function backToGiveaways() {
  // гарантируем, что navbar вернётся сразу (даже если роутер не чистит body-классы)
  document.body.classList.remove('page-creator-giveaway-card');

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
  if (!channels || channels.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = channels.map(ch => {
    const avatar = ch.avatar_url || '/miniapp-static/uploads/avatars/default_channel.png';
    const title = ch.title || ch.username || 'Канал';
    const url = ch.post_url || (ch.username ? `https://t.me/${ch.username.replace('@', '')}` : '');
    const safeTitle = title.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const safeUrl = url.replace(/"/g, '&quot;');

    return `
      <div class="pgc-channel-card">
        <div class="pgc-channel-avatar">
          <img src="${avatar}" alt="">
        </div>
        <div class="pgc-channel-title">${safeTitle}</div>
        <button
          type="button"
          class="pgc-channel-btn"
          data-channel-title="${safeTitle}"
          data-channel-url="${safeUrl}"
        >Перейти</button>
      </div>
    `;
  }).join('');

  // Делегирование — один обработчик на весь список
  container.addEventListener('click', (e) => {
    const btn = e.target.closest('.pgc-channel-btn');
    if (!btn) return;
    const channelTitle = btn.dataset.channelTitle || 'канал';
    const channelUrl = btn.dataset.channelUrl || '';
    showChannelModal(channelTitle, channelUrl);
  });
}

/**
 * Модальное окно подтверждения перехода в канал — идентично карточке участника.
 */
function showChannelModal(title, url) {
  document.getElementById('pgc-channel-modal')?.remove();

  const safeTitle = title.replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const overlay = document.createElement('div');
  overlay.id = 'pgc-channel-modal';
  overlay.className = 'pgc-channel-modal-overlay';
  overlay.innerHTML = `
    <div class="pgc-channel-modal" role="dialog" aria-modal="true">
      <p class="pgc-channel-modal__text">
        Вы действительно хотите перейти в <b>${safeTitle}</b>?
      </p>
      <div class="pgc-channel-modal__actions">
        <button type="button" class="pgc-channel-modal__btn pgc-channel-modal__btn--cancel">
          Отмена
        </button>
        <button type="button" class="pgc-channel-modal__btn pgc-channel-modal__btn--confirm">
          Перейти
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => overlay.remove();

  overlay.querySelector('.pgc-channel-modal__btn--cancel').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('.pgc-channel-modal__btn--confirm').addEventListener('click', () => {
    close();
    const tg = window.Telegram?.WebApp;
    if (url) {
      if (tg?.openTelegramLink) tg.openTelegramLink(url);
      else window.open(url, '_blank');
    }
  });
}

/**
 * Рендер описания с поддержкой Telegram HTML-разметки (<b>, <i>, \n → <br>).
 * Идентична функции в карточке участника.
 */
function renderDescription(container, rawText) {
  if (!rawText || rawText === '—') {
    container.textContent = rawText || '';
    return;
  }

  let html = rawText.replace(
    /<tg-emoji[^>]*>([\s\S]*?)<\/tg-emoji>/gi,
    (_, inner) => inner
  );

  const ALLOWED = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre'];
  const allowedPattern = new RegExp(
    `<(/?)(?:${ALLOWED.join('|')})(\\s[^>]*)?>`,
    'gi'
  );

  const placeholders = [];
  html = html.replace(allowedPattern, (match) => {
    const idx = placeholders.length;
    placeholders.push(match);
    return `\x00ALLOWED${idx}\x00`;
  });

  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  html = html.replace(/\x00ALLOWED(\d+)\x00/g, (_, idx) => placeholders[Number(idx)]);
  html = html.replace(/\r\n/g, '\n').replace(/\n/g, '<br>');

  container.innerHTML = html;
}

/**
 * Рендер блока победителей (только для завершённых розыгрышей).
 * Стиль карточек идентичен results_win / results_lose.
 */
function renderWinners(container, winners) {
  const list = Array.isArray(winners) ? winners : [];

  if (list.length === 0) {
    container.innerHTML = `
      <div class="pgc-channel-card">
        <div class="pgc-channel-title" style="color:rgba(115,115,117,1)">Победители не определены</div>
      </div>
    `;
    return;
  }

  container.innerHTML = list.map((winner, index) => {
    const position = winner.rank || (index + 1);
    let nickname = winner.username || winner.display_name || `Победитель #${position}`;
    if (nickname && !nickname.startsWith('@')) nickname = '@' + nickname.replace(/^@/, '');
    const ticketCode = winner.ticket_code || '';

    let avatarContent = '';
    if (position === 1) {
      avatarContent = `<img src="/miniapp-static/assets/images/gold-medal-image.webp" alt="1 место" class="winner-medal">`;
    } else if (position === 2) {
      avatarContent = `<img src="/miniapp-static/assets/images/silver-medal-image.webp" alt="2 место" class="winner-medal">`;
    } else if (position === 3) {
      avatarContent = `<img src="/miniapp-static/assets/images/bronze-medal-image.webp" alt="3 место" class="winner-medal">`;
    } else {
      avatarContent = `<span class="winner-position">${position}</span>`;
    }

    return `
      <div class="cgcc-winner-card">
        <div class="winner-avatar">${avatarContent}</div>
        <div class="winner-info">
          <div class="winner-name">${nickname}</div>
          ${ticketCode ? `<div class="winner-ticket">Билет: ${ticketCode}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

/**
 * Устанавливает синий фон карточки создателя в Telegram Chrome.
 * Вызывается несколько раз (0 / 50 / 150 мс) — обходим background-manager.
 */
function applyCreatorCardColors() {
  try {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    const BLUE = '#1551E5'; // rgba(21, 81, 229, 1) → hex

    if (tg.setHeaderColor)     tg.setHeaderColor(BLUE);
    if (tg.setBackgroundColor) tg.setBackgroundColor(BLUE);
    if (tg.setBottomBarColor)  tg.setBottomBarColor(BLUE);
  } catch (e) {
    console.warn('[cgcc] color sync failed', e);
  }
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

  // Прокрутка в начало (как у участника)
  window.scrollTo({ top: 0, behavior: 'auto' });

  main.innerHTML = giveawayCardCreatorTemplate();
  document.body.classList.add('page-creator-giveaway-card');

  // Синий фон + Telegram Chrome — сразу и с задержками (обходим background-manager)
  applyCreatorCardColors();
  setTimeout(applyCreatorCardColors, 50);
  setTimeout(applyCreatorCardColors, 150);

  // Подписка на themeChanged — возвращаем наш синий при смене темы
  try {
    window.Telegram?.WebApp?.onEvent?.('themeChanged', () => {
      setTimeout(applyCreatorCardColors, 10);
    });
  } catch (e) {}

  const giveawayId = sessionStorage.getItem('prizeme_creator_giveaway_id');
  if (!giveawayId) return;

  showTelegramBackButton();

  // Определяем статус из сохранённой вкладки
  const tabKey = sessionStorage.getItem(STORAGE_TAB_KEY) || 'active';
  const isCompleted = (tabKey === 'completed');

  // Бейдж статуса
  const badgeEl = main.querySelector('#cgcc-badge-status');
  if (badgeEl) {
    if (isCompleted)      badgeEl.textContent = '🏁 Завершённый';
    else if (tabKey === 'draft') badgeEl.textContent = '📝 Незапущенный';
    else                  badgeEl.textContent = '⚡ Запущенный';
  }

  const titleEl   = main.querySelector('#cgcc-title');
  const descEl    = main.querySelector('#cgcc-description');
  const endEl     = main.querySelector('#cgcc-end');
  const mediaEl   = main.querySelector('#cgcc-media');
  const channelsEl = main.querySelector('#cgcc-channels');

  loadCreatorGiveawayDetails(giveawayId)
    .then((data) => {
      titleEl.textContent = data.title || '—';
      renderDescription(descEl, data.description || '—');
      endEl.textContent = formatEndDate(data.end_at_utc);
      renderMedia(mediaEl, data.media);
      renderChannels(channelsEl, data.channels);

      // Блок победителей — только для завершённых
      if (isCompleted) {
        const winnersWrap = main.querySelector('#cgcc-winners-wrap');
        const winnersList = main.querySelector('#cgcc-winners-list');
        if (winnersWrap && winnersList) {
          winnersWrap.style.display = '';
          // Победители могут быть в data.winners (если API вернул)
          // или загружаем отдельным запросом через /api/results
          if (Array.isArray(data.winners) && data.winners.length > 0) {
            renderWinners(winnersList, data.winners);
          } else {
            loadCreatorWinners(giveawayId, winnersList);
          }
        }
      }
    })
    .catch(() => {
      titleEl.textContent = 'Ошибка загрузки';
    });

  const editBtn = main.querySelector('#cgcc-edit');
  editBtn?.addEventListener('click', () => {
    const gid = sessionStorage.getItem('prizeme_creator_giveaway_id');
    if (!gid) return;
    showEditPopup(gid);
  });
}

/**
 * Загружает победителей через /api/results для завершённого розыгрыша.
 * Используется когда основной API не возвращает data.winners.
 */
async function loadCreatorWinners(giveawayId, container) {
  try {
    const init_data = getInitData();
    if (!init_data) return;

    const r = await fetch('/api/results', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gid: giveawayId, init_data }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.ok) return;

    renderWinners(container, data.winners || []);
  } catch (e) {
    console.warn('[cgcc] loadCreatorWinners failed', e);
  }
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
