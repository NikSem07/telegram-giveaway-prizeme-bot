// ====== Рендер страниц ======

function renderHomePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="top-frame">
      <div class="top-label">Рекомендуем</div>

      <div class="top-title-row">
        <div class="top-title">
          <span class="top-title-emoji">🔥</span>
          <span class="top-title-text">Топ розыгрыши</span>
        </div>
        <button class="top-arrow" type="button" aria-label="Открыть топ">
          <span class="top-arrow-icon">&gt;</span>
        </button>
      </div>

      <div id="top-giveaways-list" class="top-list"></div>
    </div>

    <div class="section-title section-title-row" style="margin-top:18px;">
      <span>Все текущие розыгрыши</span>
      <span class="section-title-arrow">&gt;</span>
    </div>
    <div id="all-giveaways-list" style="margin-top:8px;"></div>
  `;

  loadGiveawaysLists();
}

// ====== Загрузка розыгрышей с Node.js ======

async function loadGiveawaysLists() {
  const topContainer = document.getElementById('top-giveaways-list');
  const allContainer = document.getElementById('all-giveaways-list');

  if (!topContainer || !allContainer) return;

  topContainer.innerHTML = '<div class="giveaway-card">Загружаем топ розыгрышей…</div>';
  allContainer.innerHTML = '<div class="giveaway-card">Загружаем текущие розыгрыши…</div>';

  try {
    const resp = await fetch('/api/participant_home_giveaways', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });

    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.reason || 'API error');
    }

    renderGiveawayList(topContainer, data.top || [], 'top');
    renderGiveawayList(allContainer, data.latest || [], 'all');
  } catch (err) {
    console.error('[HOME-PARTICIPANT] loadGiveawaysLists error:', err);
    topContainer.innerHTML = '<div class="giveaway-card">Не удалось загрузить розыгрыши</div>';
    allContainer.innerHTML = '';
  }
}


function renderGiveawayList(container, list, prefix) {
  container.innerHTML = '';

  if (!list.length) {
    container.innerHTML = '<div class="giveaway-card">Пока нет активных розыгрышей</div>';
    return;
  }

  list.forEach((g, index) => {
    const channels = Array.isArray(g.channels) ? g.channels : [];
    const channelsStr = channels.length ? channels.join(', ') : (g.title || 'Розыгрыш #' + g.id);
    const desc = stripTelegramMarkup(g.public_description || '');

    const timerId = `timer-${prefix}-${g.id}-${index}`;

    const isTop = prefix === 'top';

    // Поддержка полей из API (если есть)
    const firstChannelAvatarUrl =
      g.first_channel_avatar_url ||
      (Array.isArray(g.channels_meta) && g.channels_meta[0] && g.channels_meta[0].avatar_url) ||
      null;

    const participantsCount =
      typeof g.participants_count === 'number' ? g.participants_count :
      typeof g.members_count === 'number' ? g.members_count :
      null;

    const card = document.createElement('div');
    card.className = isTop ? 'giveaway-card giveaway-card--top' : 'giveaway-card giveaway-card--all';

    if (isTop) {
      card.innerHTML = `
        <div class="giveaway-left">
          <div class="giveaway-avatar giveaway-avatar--top">
            ${firstChannelAvatarUrl ? `<img src="${escapeHtml(firstChannelAvatarUrl)}" alt="">` : ``}
          </div>

          <div class="giveaway-badge ${participantsCount == null ? 'giveaway-badge--hidden' : ''}">
            <span class="giveaway-badge-icon"></span>
            <span class="giveaway-badge-text">${participantsCount == null ? '' : formatParticipants(participantsCount)}</span>
          </div>
        </div>

        <div class="giveaway-info">
          <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
          <div class="giveaway-desc">${escapeHtml(stripTelegramMarkup(desc) || 'Описание розыгрыша')}</div>
          <div class="giveaway-timer" id="${timerId}"></div>
        </div>
      `;
    } else {
      card.innerHTML = `
        <div class="giveaway-left">
          <div class="giveaway-avatar giveaway-avatar--top">
            ${firstChannelAvatarUrl ? `<img src="${escapeHtml(firstChannelAvatarUrl)}" alt="">` : ``}
          </div>

          <div class="giveaway-badge giveaway-badge--black ${participantsCount == null ? 'giveaway-badge--hidden' : ''}">
            <span class="giveaway-badge-icon"></span>
            <span class="giveaway-badge-text">${participantsCount == null ? '' : formatParticipants(participantsCount)}</span>
          </div>
        </div>

        <div class="giveaway-info">
          <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
          <div class="giveaway-desc">${escapeHtml(stripTelegramMarkup(desc) || 'Описание розыгрыша')}</div>
          <div class="giveaway-timer" id="${timerId}"></div>
        </div>
      `;
    }
    container.appendChild(card);

    if (window.updateCountdown && g.end_at_utc) {
      // Функция updateCountdown определена в app.js
      window.updateCountdown(g.end_at_utc, timerId);
    } else if (g.end_at_utc) {
      const el = document.getElementById(timerId);
      if (el) el.textContent = 'До окончания: ' + g.end_at_utc;
    }
  });
}


function stripTelegramMarkup(input) {
  if (!input) return '';

  return String(input)
    // tg-spoiler и похожие
    .replace(/<\/?tg-[^>]*>/gi, '')
    // HTML-теги
    .replace(/<[^>]*>/g, '')
    // HTML-энтити (на всякий случай)
    .replace(/&[a-z]+;/gi, '')
    // переносы строк → пробел
    .replace(/\n+/g, ' ')
    // лишние пробелы
    .replace(/\s+/g, ' ')
    .trim();
}

// ====== Форматирование счетчика участников ======

function formatParticipants(n) {
  if (typeof n !== 'number' || !isFinite(n) || n < 0) return '';

  if (n < 1000) return String(Math.floor(n));

  if (n < 100000) {
    const k = n / 1000;
    const s = k.toFixed(1).replace(/\.0$/, '');
    return `${s}к`;
  }

  if (n < 1000000) {
    return `${Math.floor(n / 1000)}к`;
  }

  const m = n / 1000000;
  const s = m.toFixed(2).replace(/\.00$/, '').replace(/0$/, '');
  return `${s}м`;
}

// ====== HELPERS ======

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}


export {
  renderHomePage,
  loadGiveawaysLists,
};