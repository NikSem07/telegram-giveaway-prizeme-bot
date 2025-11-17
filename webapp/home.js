// home.js - Логика главного экрана с навигацией
console.log('PrizeMe Home Screen loaded');

// Текущая активная страница
let currentPage = 'home';

// Переключение режимов для участника
function switchMode(mode) {
  console.log('Switching mode to:', mode);
  if (mode === 'participant') {
    window.location.href = '/miniapp/home_participant';
  } else {
    window.location.href = '/miniapp/home_creator';
  }
}

// Инициализация главного экрана
function initHomeScreen() {
    console.log('Initializing home screen with navigation...');
    
    // Загрузка статистики
    loadHomeStats();
    
    // Настройка навигации ЕСЛИ есть навбар
    if (document.querySelector('.nav-item')) {
        setupNavigation();
    }
    
    // Настройка внешнего вида Mini App
    if (window.Telegram && Telegram.WebApp) {
        Telegram.WebApp.expand();
        Telegram.WebApp.enableClosingConfirmation();
        Telegram.WebApp.setHeaderColor('#2481cc');
        Telegram.WebApp.setBackgroundColor('#f4f4f5');
        Telegram.WebApp.ready();
    }
}

// Настройка навигационного бара (для других страниц)
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const page = this.getAttribute('data-page');
            switchPage(page);
        });
    });
}

// Переключение страниц
function switchPage(page) {
    if (page === currentPage) return;
    
    console.log('Switching to page:', page);
    
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
            mainContent.innerHTML = getHomeContent();
            currentPage = 'home';
            loadHomeStats();
            break;
            
        case 'tasks':
            mainContent.innerHTML = getTasksContent();
            currentPage = 'tasks';
            break;
            
        case 'settings':
            mainContent.innerHTML = getSettingsContent();
            currentPage = 'settings';
            break;
    }
}

// Контент для главной страницы
function getHomeContent() {
    return `
        <div class="card">
            <div class="app-header">
                <h1>🎁 PrizeMe</h1>
                <p class="welcome-text">Добро пожаловать в розыгрыши!</p>
            </div>
            
            <div class="menu-grid">
                <button class="menu-btn primary" onclick="navigateToGiveaway()">
                    <span class="btn-icon">🎯</span>
                    <span class="btn-text">Участвовать в розыгрышах</span>
                </button>
                
                <button class="menu-btn secondary" onclick="showMyTickets()">
                    <span class="btn-icon">🎫</span>
                    <span class="btn-text">Мои билеты</span>
                </button>
                
                <button class="menu-btn secondary" onclick="showResults()">
                    <span class="btn-icon">🏆</span>
                    <span class="btn-text">Результаты</span>
                </button>
            </div>
            
            <div class="stats-section">
                <div class="stat-item">
                    <span class="stat-number" id="active-giveaways">0</span>
                    <span class="stat-label">активных розыгрышей</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number" id="my-tickets">0</span>
                    <span class="stat-label">моих билетов</span>
                </div>
            </div>
        </div>
    `;
}

// Контент для страницы заданий (заглушка)
function getTasksContent() {
    return `
        <div class="card">
            <div class="app-header">
                <h1>📋 Задания</h1>
                <p class="welcome-text">Выполняйте задания для участия в розыгрышах</p>
            </div>
            
            <div style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 64px; margin-bottom: 20px;">🚧</div>
                <h2>Скоро будет доступно</h2>
                <p>Раздел находится в разработке</p>
            </div>
        </div>
    `;
}

// Контент для страницы настроек (заглушка)
function getSettingsContent() {
    return `
        <div class="card">
            <div class="app-header">
                <h1>⚙️ Настройки</h1>
                <p class="welcome-text">Настройте приложение под себя</p>
            </div>
            
            <div style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 64px; margin-bottom: 20px;">🔧</div>
                <h2>Скоро будет доступно</h2>
                <p>Раздел находится в разработке</p>
            </div>
        </div>
    `;
}

// Загрузка статистики для главного экрана
function loadHomeStats() {
    setTimeout(() => {
        const activeElement = document.getElementById('active-giveaways');
        const ticketsElement = document.getElementById('my-tickets');
        
        if (activeElement) activeElement.textContent = '3';
        if (ticketsElement) ticketsElement.textContent = '2';
    }, 500);
}

// Навигация (существующие функции)
function navigateToGiveaway() {
    console.log('Navigating to giveaway participation...');
    window.location.href = '/miniapp/loading';
}

function showMyTickets() {
    console.log('Showing my tickets...');
    alert('Функция "Мои билеты" в разработке');
}

function showResults() {
    console.log('Showing results...');
    window.location.href = '/miniapp/results';
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
document.addEventListener('DOMContentLoaded', function() {
    // Проверяем, на какой странице мы находимся
    if (document.querySelector('.mode-switcher-container')) {
        // Это home_participant.html с переключалкой
        initHomeScreen();
    } else {
        // Это обычная страница с навбаром
        initParticipantNavigation();
    }
});
