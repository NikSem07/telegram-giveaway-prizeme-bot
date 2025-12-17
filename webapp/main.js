// webapp/home_participant.js — главный экран (единый для обоих режимов)

import AppState from './shared/state.js';
import Router from './shared/router.js';
import Navbar from './shared/navbar.js';
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
    
    // 1. Сначала гарантируем, что основной контейнер существует
    const mainContainer = document.getElementById('main-content');
    if (!mainContainer) {
        console.error('[HOME] Main content container not found in DOM');
        return;
    }
    
    console.log('[HOME] Main container found:', mainContainer);
    
    // 2. Инициализируем состояние
    AppState.init();
    
    // 3. Инициализируем роутер (он сам найдет контейнер)
    Router.init();
    
    // 4. Инициализируем navbar
    Navbar.init();
    
    // 5. Периодическое обновление данных на главной (только для participant)
    setInterval(() => {
        const mode = AppState.getMode();
        const page = AppState.getPage();
        
        if (mode === 'participant' && page === 'home') {
            // Используем уже импортированную функцию
            if (typeof loadGiveawaysLists === 'function') {
                loadGiveawaysLists();
            }
        }
    }, 15 * 60 * 1000); // 15 минут
});
