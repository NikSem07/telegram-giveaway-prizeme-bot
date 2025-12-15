// home_participant.js — главный экран "Участник"
console.log('[HOME-PARTICIPANT] Script loaded');

let currentPage = 'home';

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

// ====== Рендер страниц ======

function renderHomePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="profile-header" id="profile-header">
      <div class="profile-avatar">
        <img id="profile-avatar-img" src="" alt="avatar">
      </div>
      <div class="profile-info">
        <div id="profile-name">Участник PrizeMe</div>
        <div style="font-size:12px; opacity:0.7;" id="profile-username"></div>
      </div>
      <img class="profile-arrow" src="/miniapp-static/assets/icons/arrow-icon.svg" alt=">">
    </div>

    <div class="section-blue">
      <div class="section-title">Рекомендуем</div>
      <div class="section-title" style="display:flex; align-items:center; justify-content:space-between; margin-top:4px;">
        <span>🔥 Топ розыгрыши</span>
        <span style="font-size:12px; opacity:0.8;">&gt;</span>
      </div>
      <div id="top-giveaways-list" style="margin-top:10px;"></div>
    </div>

    <div class="section-title" style="margin-top:4px;">Все текущие розыгрыши ></div>
    <div id="all-giveaways-list" style="margin-top:8px;"></div>
  `;

  // Профильный хедер кликается так же, как вкладка "Профиль" в навбаре
  const header = document.getElementById('profile-header');
  if (header) {
    header.addEventListener('click', () => switchPage('profile'));
  }

  fillProfileFromTelegram();
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
  document.querySelectorAll('.bottom-nav .nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-page') === page);
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

    const nameEl = document.getElementById('profile-name');
    const usernameEl = document.getElementById('profile-username');
    const avatarEl = document.getElementById('profile-avatar-img');

    if (nameEl) {
      const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
      nameEl.textContent = name || 'Участник PrizeMe';
    }

    if (usernameEl) {
      usernameEl.textContent = user.username ? '@' + user.username : '';
    }

    // Аватар Телеги в Mini App получить нельзя, ставим заглушку
    if (avatarEl) {
      avatarEl.src = '/miniapp-static/assets/icons/profile-icon.svg';
    }
  } catch (e) {
    console.log('[HOME-PARTICIPANT] fillProfileFromTelegram error:', e);
  }
}

// Инициализация домашнего экрана участника
function initParticipantHomePage() {
  console.log('[HOME-PARTICIPANT] initParticipantHomePage');

  // тут — всё, что сейчас у тебя вызывается только при переключении вкладок:
  // - проставить активный таб "Главная"
  // - подгрузить профиль
  // - загрузить топ-розыгрыши и все текущие
  try {
    if (typeof setupNavigation === 'function') {
      setupNavigation();
    }
    if (typeof loadTopGiveaways === 'function') {
      loadTopGiveaways();
    }
    if (typeof loadRecentGiveaways === 'function') {
      loadRecentGiveaways();
    }
  } catch (e) {
    console.error('[HOME-PARTICIPANT] init error:', e);
  }
}

// Гарантируем запуск сразу после загрузки страницы
document.addEventListener('DOMContentLoaded', () => {
  // app.js уже вызвал initializeTelegramWebApp();
  if (window.location.pathname === '/miniapp/home_participant') {
    initParticipantHomePage();
  }
});


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

    const card = document.createElement('div');
    card.className = 'giveaway-card';
    card.innerHTML = `
      <div class="giveaway-avatar"></div>
      <div class="giveaway-info">
        <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
        <div class="giveaway-desc">${escapeHtml(desc || 'Описание розыгрыша')}</div>
        <div class="giveaway-timer" id="${timerId}"></div>
      </div>
    `;
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

  setupNavigation();
  switchPage('home'); // отрисуем главную сразу
});
