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

function startCountdown(leftEl, endAtUtc) {
  const tick = () => {
    leftEl.textContent = `🕒 Осталось: ${formatLeftTime(endAtUtc)}`;
  };
  tick();
  const t = setInterval(tick, 1000);
  return () => clearInterval(t);
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

function renderMedia(container, media) {
  container.innerHTML = '';

  // Figma: если медиа нет — не показываем блок вообще
  if (!media?.url) {
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  const type = (media.type || '').toLowerCase();

  if (type === 'video') {
    container.innerHTML = `<video class="pgc-media-el" playsinline preload="metadata" controls></video>`;
    const v = container.querySelector('video');
    v.src = media.url;
    return;
  }

  container.innerHTML = `<img class="pgc-media-el" src="${media.url}" alt="">`;
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

  const giveawayId = sessionStorage.getItem('prizeme_participant_giveaway_id');
  if (!giveawayId) return;

  const titleEl = main.querySelector('#pgc-title');
  const leftEl = main.querySelector('#pgc-left');
  const descEl = main.querySelector('#pgc-description');
  const mediaEl = main.querySelector('#pgc-media');
  const ticketsEl = main.querySelector('#pgc-tickets-list');
  const channelsEl = main.querySelector('#pgc-channels');
  const openBtn = main.querySelector('#pgc-open');

  titleEl.textContent = 'Загрузка...';
  leftEl.textContent = '🕒 Осталось: —';
  descEl.textContent = '';

  let stopCountdown = null;
  loadParticipantGiveawayDetails(giveawayId)
    .then((data) => {
        // title
        titleEl.textContent = data.title || '—';

        // description
        descEl.textContent = data.description || '—';

        // media (Figma: если медиа нет — блок не показываем)
        renderMedia(mediaEl, data.media);

        // tickets
        renderTickets(ticketsEl, data.tickets);

        // channels
        renderChannels(channelsEl, data.channels);

        // countdown
        if (stopCountdown) stopCountdown();
        stopCountdown = startCountdown(leftEl, data.end_at_utc);

        // button → post
        openBtn.disabled = !(data.post_url || data.channels?.[0]?.post_url);
        openBtn.addEventListener('click', () => openGiveawayPost(data));
    })
    .catch((err) => {
        console.error('[giveaway_card_participant] load error:', err);
        titleEl.textContent = 'Ошибка загрузки';
        leftEl.textContent = '🕒 Осталось: —';
        descEl.textContent = '';
        openBtn.disabled = true;
    });
}

export { renderGiveawayCardParticipantPage, hideTelegramBackButton };
