// webapp/pages/participant/giveaways/giveaway_card_participant.js
import giveawayCardParticipantTemplate from './giveaway_card_participant.template.js';
import Router from '../../../shared/router.js';

const STORAGE_TAB_KEY = 'prizeme_participant_giveaways_tab';

function backToGiveaways() {
  // вернуть UI Telegram в исходное состояние
  const tg = window.Telegram?.WebApp;
  if (tg?.BackButton) {
    try { tg.BackButton.offClick(backToGiveaways); } catch (e) {}
    tg.BackButton.hide();
  }

  document.body.classList.remove('page-participant-giveaway-card');
  Router.navigate('giveaways');
}

function getInitData() {
  return sessionStorage.getItem('prizeme_init_data') || window.Telegram?.WebApp?.initData || '';
}

function showTelegramBackButton() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.BackButton) return;

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

function ensureOnlyThisBodyClass() {
  document.body.classList.remove('page-creator-giveaway-card');
  document.body.classList.add('page-participant-giveaway-card');
}

function formatLeftTime(endAtUtc) {
  if (!endAtUtc) return '—';
  const end = new Date(endAtUtc);
  const now = new Date();
  const diff = end.getTime() - now.getTime();
  if (Number.isNaN(end.getTime()) || diff <= 0) return '0д 00:00:00';

  const totalSec = Math.floor(diff / 1000);
  const days = Math.floor(totalSec / 86400);
  const h = Math.floor((totalSec % 86400) / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;

  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return `${days}д ${hh}:${mm}:${ss}`;
}

function startCountdown(leftTimeEl, endAtUtc) {
  const tick = () => {
    leftTimeEl.textContent = formatLeftTime(endAtUtc);
  };
  tick();
  const t = setInterval(tick, 1000);
  return () => clearInterval(t);
}

function formatDateDDMMYYYY(endAtUtc) {
  if (!endAtUtc) return '—';
  const d = new Date(endAtUtc);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yy = d.getFullYear();
  return `${dd}.${mm}.${yy}`;
}

async function loadResultsForGid(gid) {
  const init_data = getInitData();
  if (!init_data) throw new Error('no_init_data_results');

  // ВАЖНО: в твоём app_js.txt resultsFlow вызывает api("/api/results", { gid, init_data })
  // поэтому тут делаем так же.
  const resp = await fetch('/api/results', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gid: String(gid), init_data }),
  });

  const data = await resp.json().catch(() => null);
  if (!resp.ok || !data || !data.ok) {
    throw new Error(data?.reason || `http_${resp.status}`);
  }
  return data;
}

function applyFinishedTheme(isWinner) {
  const body = document.body;
  const html = document.documentElement;

  body.classList.remove('pgc-finished-win', 'pgc-finished-lose');
  html.classList.remove('pgc-finished-win', 'pgc-finished-lose');

  const cls = isWinner ? 'pgc-finished-win' : 'pgc-finished-lose';
  body.classList.add(cls);
  html.classList.add(cls);

  const bg = isWinner ? '#024B42' : '#570C07';

  // Telegram WebView цвета (иначе может "откатить" назад)
  const top = isWinner ? '#024B42' : '#570C07';
  const bottom = '#1c1c1c';

  try {
    const tg = window.Telegram?.WebApp;
    if (tg?.setHeaderColor) tg.setHeaderColor(top);
    if (tg?.setBackgroundColor) tg.setBackgroundColor(bottom);
    if (tg?.setBottomBarColor) tg.setBottomBarColor(bottom);
  } catch (e) {}
}


async function loadParticipantGiveawayDetails(giveawayId) {
  const init_data = getInitData();
  if (!init_data) throw new Error('no_init_data');

  // ВАЖНО: этот endpoint должен вернуть:
  // { ok:true, title, description, end_at_utc, media:{url,type}, channels:[{title,username,avatar_url,post_url}], tickets:[...], post_url? }
  const r = await fetch('/api/participant_giveaway_details', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data, giveaway_id: giveawayId }),
  });

  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.ok) throw new Error(data?.reason || 'server_error');
  return data;
}

function renderMedia(container, media, data) {
  container.innerHTML = '';

  // 1) Нормализуем url из разных возможных форматов ответа
  let url =
    (typeof media === 'string' ? media : null) ||
    media?.url ||
    media?.media_url ||
    media?.mediaUrl ||
    data?.media_url ||
    data?.mediaUrl ||
    data?.media;

  // если пришёл объект, но не в url — пробуем вложенность
  if (!url && typeof data?.media === 'object' && data?.media) {
    url = data.media.url || data.media.media_url || data.media.mediaUrl;
  }

  if (!url) {
    container.style.display = 'none';
    return;
  }

  // 2) Подстраховка: относительные пути без "/" превращаем в "/..."
  if (typeof url === 'string' && !url.startsWith('http') && !url.startsWith('/')) {
    url = `/${url}`;
  }

  // 3) Тип: берём из ответа или определяем по расширению
  let type =
    (typeof media === 'object' ? (media?.type || media?.media_type) : null) ||
    data?.media_type ||
    '';

  type = String(type).toLowerCase();

  if (!type) {
    const lower = String(url).toLowerCase();
    if (lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.includes('video')) type = 'video';
    else type = 'image';
  }

  container.style.display = '';

  if (type === 'video') {
    container.innerHTML = `<video class="pgc-media-el" playsinline preload="metadata" controls></video>`;
    const v = container.querySelector('video');
    v.src = url;
    return;
  }

  container.innerHTML = `<img class="pgc-media-el" src="${url}" alt="" loading="eager" decoding="async">`;
  const img = container.querySelector('img');
  try { img.fetchPriority = 'high'; } catch (e) {}
}


function renderTickets(container, tickets) {
  const list = (tickets || []).filter(Boolean);
  if (list.length === 0) {
    container.innerHTML = `<div class="pgc-media-empty">Билетов нет</div>`;
    return;
  }

  container.innerHTML = list.map(t => {
    const label = (typeof t === 'string' || typeof t === 'number') ? String(t) : (t.code || t.ticket || t.id || '—');
    return `<div class="pgc-ticket-pill">${label}</div>`;
  }).join('');
}

function renderChannels(container, channels) {
  container.innerHTML = (channels || []).map(ch => {
    const avatar = ch.avatar_url || '/miniapp-static/assets/images/default-avatar.webp';
    const title = ch.title || ch.username || 'Канал';

    return `
      <div class="pgc-channel-card">
        <div class="pgc-channel-avatar">
          <img src="${avatar}" alt="">
        </div>
        <div class="pgc-channel-title">${title}</div>
      </div>
    `;
  }).join('');
}

function openGiveawayPost(data) {
  // 1) приоритет: data.post_url
  // 2) fallback: channels[0].post_url
  const url = data?.post_url || data?.channels?.[0]?.post_url;

  if (!url) {
    const tg = window.Telegram?.WebApp;
    if (tg?.showAlert) tg.showAlert('Ссылка на пост не найдена');
    return;
  }

  const tg = window.Telegram?.WebApp;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url); // мини-апп свернется
    return;
  }

  window.open(url, '_blank');
}

function renderGiveawayCardParticipantPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = giveawayCardParticipantTemplate();
  ensureOnlyThisBodyClass();
  showTelegramBackButton();

  try {
    const tg = window.Telegram?.WebApp;
    if (tg?.setHeaderColor) tg.setHeaderColor('#1551e5');  // верх
    if (tg?.setBackgroundColor) tg.setBackgroundColor('#1c1c1c'); // низ
    if (tg?.setBottomBarColor) tg.setBottomBarColor('#1c1c1c');
  } catch (e) {}

  const giveawayId = sessionStorage.getItem('prizeme_participant_giveaway_id');
  if (!giveawayId) return;

  const titleEl = main.querySelector('#pgc-title');
  const leftTimeEl = main.querySelector('#pgc-left-time');
  const statusBadgeEl = main.querySelector('#pgc-badge-status');
  const secondaryLabelEl = main.querySelector('#pgc-badge-secondary-label');
  const winnerBadgeEl = main.querySelector('#pgc-badge-winner');
  const descEl = main.querySelector('#pgc-description');
  const mediaEl = main.querySelector('#pgc-media');
  const ticketsEl = main.querySelector('#pgc-tickets-list');
  const channelsEl = main.querySelector('#pgc-channels');
  const openBtn = main.querySelector('#pgc-open');

  if (!titleEl || !leftTimeEl || !descEl || !mediaEl || !ticketsEl || !channelsEl || !openBtn
      || !statusBadgeEl || !secondaryLabelEl || !winnerBadgeEl) {
    console.error('[giveaway_card_participant] missing DOM nodes');
    return;
  }

  titleEl.textContent = 'Загрузка...';
  leftTimeEl.textContent = '—';
  descEl.textContent = '';

  let stopCountdown = null;
  loadParticipantGiveawayDetails(giveawayId)
    .then((data) => {
        // title
        titleEl.textContent = data.title || '—';

        // description
        descEl.textContent = data.description || '—';

        // media (Figma: если медиа нет — блок не показываем)
        renderMedia(mediaEl, data.media, data);

        // tickets
        renderTickets(ticketsEl, data.tickets);

        // channels
        renderChannels(channelsEl, data.channels);

        // countdown OR finished date
        if (stopCountdown) stopCountdown();
        stopCountdown = null;

        const mode = sessionStorage.getItem('prizeme_participant_card_mode') || 'active';
        const status = String(data.status || '').toLowerCase();

        // finished режим определяем по табу (mode) или по статусу из API
        const isFinished = (mode === 'finished') || (status === 'finished');

        if (isFinished) {
        // Бейджи
        statusBadgeEl.textContent = '🏁 Завершенный';
        secondaryLabelEl.textContent = '📅 Дата завершения:';
        leftTimeEl.textContent = formatDateDDMMYYYY(data.end_at_utc);

        // Кнопка: результат
        openBtn.disabled = false;
        openBtn.textContent = 'Посмотреть результат';
        openBtn.onclick = () => {
        // помечаем, что в results мы пришли из карточки
        sessionStorage.setItem('prizeme_results_from_card', '1');
        sessionStorage.setItem('prizeme_results_back_gid', String(giveawayId));
        sessionStorage.setItem('prizeme_participant_card_mode', 'finished');

        window.location.href = `/miniapp/loading?gid=results_${encodeURIComponent(String(giveawayId))}`;
        };

        // Узнаем win/lose и красим
        loadResultsForGid(giveawayId)
            .then((results) => {
            const isWinner = !!(results.user && results.user.is_winner);
            winnerBadgeEl.textContent = isWinner ? '🏆 Вы победили' : '🎟️ Вы не победили';
            applyFinishedTheme(isWinner);
            })
            .catch(() => {
            // фоллбек без падения карточки
            winnerBadgeEl.textContent = '🎟️ Результаты недоступны';
            });

        } else {
        // ACTIVE (как было)
        statusBadgeEl.textContent = '⌛ Активный';
        secondaryLabelEl.textContent = '🕒 Осталось:';
        stopCountdown = startCountdown(leftTimeEl, data.end_at_utc);

        openBtn.disabled = !(data.post_url || data.channels?.[0]?.post_url);
        openBtn.textContent = 'Перейти к розыгрышу';
        openBtn.onclick = () => openGiveawayPost(data);
        }

    })
    .catch((err) => {
        console.error('[giveaway_card_participant] load error:', err);
        titleEl.textContent = 'Ошибка загрузки';
        leftTimeEl.textContent = '—';
        descEl.textContent = '';
        openBtn.disabled = true;
    });
}

export { renderGiveawayCardParticipantPage, hideTelegramBackButton };
