import { renderHomePage, loadGiveawaysLists } from './pages/participant/home/home.js';
import { setupNavigation, switchPage, getCurrentPage } from './pages/participant/router.js';
import { renderProfilePage } from './pages/participant/profile/profile.js';

// home_participant.js — главный экран "Участник"
console.log('[HOME-PARTICIPANT] Script loaded');

// Переключение режима Участник / Создатель
function switchMode(mode) {
  window.switchMode = switchMode;
  console.log('[HOME-PARTICIPANT] switchMode:', mode);
  if (mode === 'creator') {
    window.location.href = '/miniapp/home_creator';
  } else {
    window.location.href = '/miniapp/home_participant';
  }
}

function renderTasksPage() {
  window.renderTasksPage = renderTasksPage;
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
  window.renderGiveawaysPage = renderGiveawaysPage;
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">🎯 Мои розыгрыши</h2>
      <p class="stub-text">Здесь появятся ваши активные и прошедшие розыгрыши. Раздел находится в разработке.</p>
    </div>
  `;
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
    if (getCurrentPage() === 'home') {
      loadGiveawaysLists();
    }
  }, 15 * 60 * 1000);

});
