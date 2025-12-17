// webapp/home_participant.js — главный экран (единый для обоих режимов)

import AppState from './shared/state.js';
import Router from './shared/router.js';
import Navbar from './shared/navbar.js';
import { fillProfileFromTelegram } from './pages/participant/profile/profile.js';
import { loadGiveawaysLists } from './pages/participant/home/home.js';

console.log('[HOME] Script loaded');

// Переключение режима Участник / Создатель
function switchMode(mode) {
    console.log('[HOME] switchMode:', mode);
    
    if (mode !== 'participant' && mode !== 'creator') {
        console.error('[HOME] Invalid mode:', mode);
        return;
    }
    
    // Обновляем визуальные кнопки переключателя
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    
    // Обновляем состояние приложения
    AppState.setMode(mode);
    
    // Навигация на главную страницу выбранного режима
    Router.navigate('home');
}

window.switchMode = switchMode;

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    console.log('[HOME] DOM ready');
    
    // Инициализируем состояние
    AppState.init();
    
    // Загружаем аватар из Telegram для навбара
    // Используем задержку, чтобы DOM успел загрузиться
    setTimeout(() => {
        const user = fillProfileFromTelegram();
        if (user && user.photo_url) {
            // Обновляем аватар в navbar через Navbar API
            Navbar.updateAvatar(user.photo_url);
        }
    }, 300);
    
    // Инициализируем роутер
    Router.init();
    
    // Инициализируем navbar
    Navbar.init();

    // Подписываемся на изменения страницы для обновления аватара на странице профиля
    AppState.subscribe((state) => {
        if (state.changed === 'page' && state.page === 'profile') {
            // Небольшая задержка, чтобы DOM успел отрендериться
            setTimeout(() => {
                const tg = window.Telegram && Telegram.WebApp;
                const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
                if (user && user.photo_url) {
                    // Обновляем аватар на странице профиля
                    const profileAvatar = document.getElementById('profile-page-avatar');
                    if (profileAvatar) {
                        profileAvatar.src = user.photo_url;
                    }
                }
            }, 50);
        }
    });
    
    // Периодическое обновление данных на главной (только для participant)
    setInterval(() => {
        const mode = AppState.getMode();
        const page = AppState.getPage();
        
        if (mode === 'participant' && page === 'home') {
            loadGiveawaysLists();
        }
    }, 15 * 60 * 1000); // 15 минут
});
