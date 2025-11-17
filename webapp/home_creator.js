// home_creator.js - Логика для версии создателя
console.log('PrizeMe Creator loaded');

let currentPage = 'home';

// Переключение режимов
function switchMode(mode) {
  console.log('Creator: Switching mode to:', mode);
  if (mode === 'participant') {
    window.location.href = '/miniapp/home_participant';
  } else {
    window.location.href = '/miniapp/home_creator';
  }
}

// Инициализация создателя
function initCreatorScreen() {
  console.log('Initializing creator screen...');
  
  // Загрузка статистики
  loadCreatorStats();
  
  // Настройка навигации
  setupCreatorNavigation();
  
  // Настройка Telegram WebApp
  if (window.Telegram && Telegram.WebApp) {
    Telegram.WebApp.expand();
    Telegram.WebApp.enableClosingConfirmation();
    Telegram.WebApp.setHeaderColor('#2481cc');
    Telegram.WebApp.setBackgroundColor('#f4f4f5');
  }
}

// Настройка навигации создателя
function setupCreatorNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  
  navItems.forEach(item => {
    item.addEventListener('click', function() {
      const page = this.getAttribute('data-page');
      switchCreatorPage(page);
    });
  });
}

// Переключение страниц создателя
function switchCreatorPage(page) {
  if (page === currentPage) return;
  
  // Обновляем активный элемент навбара
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  document.querySelector(`[data-page="${page}"]`).classList.add('active');
  
  // Управляем видимостью переключалки
  const body = document.body;
  if (page === 'home') {
    body.classList.add('home-page');
  } else {
    body.classList.remove('home-page');
  }
  
  // Показываем соответствующий контент
  const mainContent = document.getElementById('main-content');
  
  switch(page) {
    case 'home':
      mainContent.innerHTML = getCreatorHomeContent();
      currentPage = 'home';
      loadCreatorStats();
      break;
      
    case 'services':
      mainContent.innerHTML = getCreatorServicesContent();
      currentPage = 'services';
      break;
      
    case 'giveaways':
      mainContent.innerHTML = getCreatorGiveawaysContent();
      currentPage = 'giveaways';
      break;
      
    case 'stats':
      mainContent.innerHTML = getCreatorStatsContent();
      currentPage = 'stats';
      break;
  }
}

// Контент для главной создателя
function getCreatorHomeContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>🎁 PrizeMe Creator</h1>
        <p class="welcome-text">Панель управления розыгрышами</p>
      </div>
      
      <div class="menu-grid">
        <button class="menu-btn primary" onclick="createGiveaway()">
          <span class="btn-icon">➕</span>
          <span class="btn-text">Создать розыгрыш</span>
        </button>
        
        <button class="menu-btn secondary" onclick="showMyGiveaways()">
          <span class="btn-icon">📋</span>
          <span class="btn-text">Мои розыгрыши</span>
        </button>
        
        <button class="menu-btn secondary" onclick="showStatistics()">
          <span class="btn-icon">📊</span>
          <span class="btn-text">Статистика</span>
        </button>
      </div>
      
      <div class="stats-section">
        <div class="stat-item">
          <span class="stat-number" id="active-giveaways">0</span>
          <span class="stat-label">активных</span>
        </div>
        <div class="stat-item">
          <span class="stat-number" id="total-participants">0</span>
          <span class="stat-label">участников</span>
        </div>
        <div class="stat-item">
          <span class="stat-number" id="completed-giveaways">0</span>
          <span class="stat-label">завершено</span>
        </div>
      </div>
    </div>
  `;
}

// Контент для сервисов создателя
function getCreatorServicesContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>🛠️ Сервисы</h1>
        <p class="welcome-text">Дополнительные инструменты</p>
      </div>
      
      <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 64px; margin-bottom: 20px;">🚧</div>
        <h2>Скоро будет доступно</h2>
        <p>Раздел находится в разработке</p>
      </div>
    </div>
  `;
}

// Контент для розыгрышей создателя
function getCreatorGiveawaysContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>🎯 Розыгрыши</h1>
        <p class="welcome-text">Управление вашими розыгрышами</p>
      </div>
      
      <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 64px; margin-bottom: 20px;">🚧</div>
        <h2>Скоро будет доступно</h2>
        <p>Раздел находится в разработке</p>
      </div>
    </div>
  `;
}

// Контент для статистики создателя
function getCreatorStatsContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>📊 Статистика</h1>
        <p class="welcome-text">Аналитика и отчеты</p>
      </div>
      
      <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 64px; margin-bottom: 20px;">🚧</div>
        <h2>Скоро будет доступно</h2>
        <p>Раздел находится в разработке</p>
      </div>
    </div>
  `;
}

// Загрузка статистики создателя
function loadCreatorStats() {
  setTimeout(() => {
    const activeElement = document.getElementById('active-giveaways');
    const participantsElement = document.getElementById('total-participants');
    const completedElement = document.getElementById('completed-giveaways');
    
    if (activeElement) activeElement.textContent = '3';
    if (participantsElement) participantsElement.textContent = '156';
    if (completedElement) completedElement.textContent = '12';
  }, 500);
}

// Функции создателя
function createGiveaway() {
  console.log('Creating new giveaway...');
  alert('Функция "Создать розыгрыш" в разработке');
}

function showMyGiveaways() {
  console.log('Showing my giveaways...');
  alert('Функция "Мои розыгрыши" в разработке');
}

function showStatistics() {
  console.log('Showing statistics...');
  alert('Функция "Статистика" в разработке');
}

// Убедимся что при загрузке переключалка видна
function ensureHomePageClass() {
    if (currentPage === 'home') {
        document.body.classList.add('home-page');
    }
}

// Вызываем при инициализации
ensureHomePageClass();

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', initCreatorScreen);
