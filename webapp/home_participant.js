import { loadGiveawaysLists } from './pages/participant/home/home.js';
import { setupNavigation, switchPage, getCurrentPage } from './pages/participant/router.js';
import { fillProfileFromTelegram } from './pages/participant/profile/profile.js';

// home_participant.js — главный экран "Участник"
console.log('[HOME-PARTICIPANT] Script loaded');

// Переключение режима Участник / Создатель
function switchMode(mode) {
  console.log('[HOME] switchMode:', mode);

  // визуально переключаем активную кнопку
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // остаёмся в одном layout и просто рендерим другую "главную"
  if (mode === 'creator') {
    switchPage('creator-home');
  } else {
    switchPage('home');
  }
}

window.switchMode = switchMode;

// ====== Инициализация ======
document.addEventListener('DOMContentLoaded', () => {
  console.log('[HOME-PARTICIPANT] DOM ready');

  // Подгружаем аватар из Telegram один раз (аватар в навбаре)
  fillProfileFromTelegram();

  setupNavigation();
  switchPage('home'); // стартуем с главной

    // Обновляем данные (включая счетчики) раз в 15 мин, когда открыта главная
  setInterval(() => {
    if (getCurrentPage() === 'home') {
      loadGiveawaysLists();
    }
  }, 15 * 60 * 1000);

});
