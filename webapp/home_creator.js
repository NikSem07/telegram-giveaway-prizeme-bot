import { setupNavigation, switchPage } from './pages/creator/router.js';

// home_creator.js - Логика для версии создателя
console.log('PrizeMe Creator loaded');

// Переключение режимов
function switchMode(mode) {
  console.log('Creator: Switching mode to:', mode);
  if (mode === 'participant') {
    window.location.href = '/miniapp/home_participant';
  } else {
    window.location.href = '/miniapp/home_creator';
  }
}
window.switchMode = switchMode;

// Инициализация создателя
function initCreatorScreen() {
  // Telegram WebApp
  if (window.Telegram && Telegram.WebApp) {
    Telegram.WebApp.expand();
    Telegram.WebApp.enableClosingConfirmation();
    Telegram.WebApp.setHeaderColor('#2481cc');
    Telegram.WebApp.setBackgroundColor('#f4f4f5');
  }

  setupNavigation();
  switchPage('home');
}

// Функции создателя
function createGiveaway() {
  console.log('Creating new giveaway...');
  alert('Функция "Создать розыгрыш" в разработке');
}
window.createGiveaway = createGiveaway;

function showMyGiveaways() {
  console.log('Showing my giveaways...');
  alert('Функция "Мои розыгрыши" в разработке');
}
window.showMyGiveaways = showMyGiveaways;

function showStatistics() {
  console.log('Showing statistics...');
  alert('Функция "Статистика" в разработке');
}
window.showStatistics = showStatistics;

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', initCreatorScreen);
