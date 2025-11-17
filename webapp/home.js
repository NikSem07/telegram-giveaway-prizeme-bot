// home.js - Логика главного экрана
console.log('PrizeMe Home Screen loaded');

// Инициализация главного экрана
function initHomeScreen() {
    console.log('Initializing home screen...');
    
    // Здесь будет загрузка статистики
    loadHomeStats();
    
    // Настройка внешнего вида Mini App
    if (window.Telegram && Telegram.WebApp) {
        Telegram.WebApp.expand();
        Telegram.WebApp.enableClosingConfirmation();
        Telegram.WebApp.setHeaderColor('#2481cc');
        Telegram.WebApp.setBackgroundColor('#f4f4f5');
    }
}

// Загрузка статистики для главного экрана
function loadHomeStats() {
    // Заглушка - здесь будет реальный API запрос
    setTimeout(() => {
        document.getElementById('active-giveaways').textContent = '3';
        document.getElementById('my-tickets').textContent = '2';
    }, 500);
}

// Навигация
function navigateToGiveaway() {
    console.log('Navigating to giveaway participation...');
    // Перенаправляем на стандартный flow участия
    window.location.href = '/miniapp/loading';
}

function showMyTickets() {
    console.log('Showing my tickets...');
    // Здесь будет переход к списку билетов
    alert('Функция "Мои билеты" в разработке');
}

function showResults() {
    console.log('Showing results...');
    // Здесь будет переход к результатам
    window.location.href = '/miniapp/results';
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', initHomeScreen);