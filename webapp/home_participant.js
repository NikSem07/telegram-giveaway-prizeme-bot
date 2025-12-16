// home_participant.js — главный экран "Участник"
console.log('[HOME-PARTICIPANT] Script loaded');

let currentPage = null;

// Переключение режима Участник / Создатель
function switchMode(mode) {
  console.log('[HOME-PARTICIPANT] switchMode:', mode);
  if (mode === 'creator') {
    window.location.href = '/miniapp/home_creator';
  } else {
    window.location.href = '/miniapp/home_participant';
  }
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

function firstLine(str, maxLen) {
  if (!str) return '';
  const line = str.split('\n')[0].trim();
  if (maxLen && line.length > maxLen) {
    return line.slice(0, maxLen - 1) + '…';
  }
  return line;
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

    <div class="section-title" style="margin-top:18px;">Все текущие розыгрыши ></div>
    <div id="all-giveaways-list" style="margin-top:8px;"></div>
  `;

  loadGiveawaysLists();
}

function renderTasksPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">📋 Задания</h2>
      <p class="stub-text">Выполняйте задания, чтобы участвовать в розыгрышах. Раздел находится в разработке.</p>
    </div>
  `;
}

function renderGiveawaysPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">🎯 Мои розыгрыши</h2>
      <p class="stub-text">Здесь появятся ваши активные и прошедшие розыгрыши. Раздел находится в разработке.</p>
    </div>
  `;
}

function renderProfilePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">👤 Профиль</h2>
      <p class="stub-text">Здесь позже появятся настройки профиля, ваш прогресс и история участия.</p>
    </div>
  `;
}

// ====== Навигация по нижнему бару ======

function setupNavigation() {
  const items = document.querySelectorAll('.bottom-nav .nav-item');
  items.forEach(item => {
    item.addEventListener('click', () => {
      const page = item.getAttribute('data-page');
      switchPage(page);
    });
  });
}

function switchPage(page) {
  if (!page || page === currentPage) return;
  currentPage = page;

  // Обновляем активный элемент навбара
  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.dataset.page === page) {
        item.classList.add('active');
    } else {
        item.classList.remove('active');
    }
  });

  // Переключаем контент
  if (page === 'home') {
    document.body.classList.add('home-page');
    renderHomePage();
  } else {
    document.body.classList.remove('home-page');
    if (page === 'tasks') renderTasksPage();
    else if (page === 'giveaways') renderGiveawaysPage();
    else if (page === 'profile') renderProfilePage();
  }
}

// ====== Профиль из Telegram WebApp ======
function fillProfileFromTelegram() {
  try {
    const tg = window.Telegram && Telegram.WebApp;
    const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!user) return;

    const avatarEl = document.getElementById('nav-profile-avatar');
    if (!avatarEl) return;

    if (user.photo_url) {
      // Telegram иногда отдаёт прямой URL аватара в user.photo_url
      avatarEl.src = user.photo_url;
    } else {
      // fallback — стандартная иконка профиля
      avatarEl.src = '/miniapp-static/assets/icons/profile-icon.svg';
    }
  } catch (e) {
    console.log('[HOME-PARTICIPANT] fillProfileFromTelegram error:', e);
  }
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
    const desc = firstLine(g.public_description || '', 60);

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
    card.className = isTop ? 'giveaway-card giveaway-card--top' : 'giveaway-card';

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

        <div class="giveaway-info giveaway-info--top">
          <div class="giveaway-channels">${escapeHtml(channelsStr)}</div>
          <div class="giveaway-desc giveaway-desc--top">${escapeHtml(desc || 'Описание розыгрыша')}</div>
          <div class="giveaway-timer giveaway-timer--top" id="${timerId}"></div>
        </div>
      `;
    } else {
      card.innerHTML = `
        <div class="giveaway-avatar"></div>
        <div class="giveaway-info">
          <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
          <div class="giveaway-desc">${escapeHtml(desc || 'Описание розыгрыша')}</div>
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

// ====== Инициализация ======
document.addEventListener('DOMContentLoaded', () => {
  console.log('[HOME-PARTICIPANT] DOM ready');

  // Убедимся, что body помечен как home-page (чтобы показывалась переключалка)
  document.body.classList.add('home-page');

  // Подгружаем аватар из Telegram один раз
  fillProfileFromTelegram();

  setupNavigation();
  switchPage('home'); // отрисуем главную сразу

    // Обновляем данные (включая счетчики) раз в час, когда открыта главная
  setInterval(() => {
    if (currentPage === 'home') {
      loadGiveawaysLists();
    }
  }, 60 * 60 * 1000);

});
