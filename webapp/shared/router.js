// webapp/shared/router.js
// Универсальный роутер, учитывающий режим (participant/creator)

import AppState from './state.js';

// Импортируем все render-функции
import { renderHomePage as renderParticipantHome } from '../pages/participant/home/home.js';
import { renderTasksPage } from '../pages/participant/tasks/tasks.js';
import { renderGiveawaysPage as renderParticipantGiveaways } from '../pages/participant/giveaways/giveaways.js';
import { renderGiveawayCardParticipantPage } from '../pages/participant/giveaways/giveaway_card_participant.js';
import { renderProfilePage } from '../pages/participant/profile/profile.js';

import { renderCreatorHomePage } from '../pages/creator/home/home.js';
import { renderServicesPage } from '../pages/creator/services/services.js';
import { renderGiveawaysPage as renderCreatorGiveaways } from '../pages/creator/giveaways/giveaways.js';
import { renderGiveawayCardCreatorPage } from '../pages/creator/giveaways/giveaway_card_creator.js';
import { renderStatsPage } from '../pages/creator/stats/stats.js';

// --- Mode page mapping (keep section when switching modes) ---
const MODE_PAGE_MAP = {
  participant: { // switching TO participant (from creator)
    home: 'home',
    services: 'tasks',
    giveaways: 'giveaways',
    stats: 'profile',
    giveaway_card_creator: 'giveaways',
    giveaway_card_participant: 'giveaways'
  },
  creator: { // switching TO creator (from participant)
    home: 'home',
    tasks: 'services',
    giveaways: 'giveaways',
    profile: 'stats',
    giveaway_card_participant: 'giveaways'
  }
};

const Router = {
    // Карта маршрутов: mode -> page -> renderFunction
    routes: {
        participant: {
        home: renderParticipantHome,
        tasks: renderTasksPage,
        giveaways: renderParticipantGiveaways,
        giveaway_card_participant: renderGiveawayCardParticipantPage,
        profile: renderProfilePage
        },

        creator: {
        home: renderCreatorHomePage,
        services: renderServicesPage,
        giveaways: renderCreatorGiveaways,
        giveaway_card_creator: renderGiveawayCardCreatorPage,
        stats: renderStatsPage
        }
    },
    
    // Текущий рендер-контейнер
    container: null,

    // Для корректного переключения режимов без сброса раздела
    lastMode: null,
    lastPageByMode: {
        participant: 'home',
        creator: 'home'
    },
    
    // Инициализация
    init() {
        this.container = document.getElementById('main-content');
        if (!this.container) {
            console.error('[ROUTER] Main content container not found');
            return;
        }
        
        console.log('[ROUTER] Initialized');

        this.lastMode = AppState.getMode();
        this.lastPageByMode[this.lastMode] = AppState.getPage() || 'home';
        
        // Подписываемся на изменения состояния
        AppState.subscribe((state) => {
            // 1) Смена страницы в текущем режиме — просто навигируем
            if (state.changed === 'page') {
                this.navigate(state.page || 'home');
                return;
            }

            // 2) Смена режима — маппим раздел и навигируем в "эквивалент"
            if (state.changed === 'mode') {
                const newMode = AppState.getMode();
                const prevMode = this.lastMode || (newMode === 'creator' ? 'participant' : 'creator');

                // Берём последнюю страницу, на которой был пользователь в предыдущем режиме
                const fromPage = this.lastPageByMode[prevMode] || AppState.getPage() || 'home';

                // Маппим в страницу нового режима
                const targetPage = (MODE_PAGE_MAP[newMode] && MODE_PAGE_MAP[newMode][fromPage]) ? MODE_PAGE_MAP[newMode][fromPage] : 'home';

                // Обновляем lastMode
                this.lastMode = newMode;
                this.lastPageByMode[newMode] = targetPage;

                this.navigate(targetPage);
                return;
            }
        });
        
        // Инициализируем начальную страницу
        this.navigate(AppState.getPage() || 'home');
    },
    
    // Навигация на страницу
    navigate(page) {
        if (!page) return;
        
        const mode = AppState.getMode();
        
        // Проверяем, существует ли маршрут
        if (!this.routes[mode] || !this.routes[mode][page]) {
            console.warn(`[ROUTER] Route not found: ${mode}/${page}`);
            
            // Fallback: для creator -> home, для participant -> home
            if (mode === 'creator') {
                page = 'home';
            } else {
                page = 'home';
            }
        }
        
        // Обновляем lastPageByMode (важно для корректного mode-switch)
        this.lastPageByMode[mode] = page;

        // Не триггерим лишние события, если page не изменилась
        if (AppState.getPage() !== page) {
            AppState.setPage(page);
        }
        
        // Вызываем render-функцию
        this.render(page);
    },
    
    // Рендер страницы
    render(page) {
        const mode = AppState.getMode();
        const renderFn = this.routes[mode][page];
        
        if (!renderFn || typeof renderFn !== 'function') {
            console.error(`[ROUTER] No render function for: ${mode}/${page}`);
            this.showFallback();
            return;
        }
        
        // ГАРАНТИРУЕМ, что контейнер существует
        if (!this.container) {
            console.warn('[ROUTER] Container not ready, delaying render...');
            setTimeout(() => this.render(page), 100);
            return;
        }
        
        // Дополнительная проверка: контейнер должен быть в DOM
        if (!this.container.isConnected) {
            console.warn('[ROUTER] Container not in DOM, delaying render...');
            setTimeout(() => this.render(page), 100);
            return;
        }
        
        try {
            console.log(`[ROUTER] Rendering: ${mode}/${page}`);
            renderFn();
            
            // ТОЛЬКО логируем состояние контейнера, не пытаемся перерендерить
            if (this.container.innerHTML.trim() === '') {
                console.log('[ROUTER] Container is empty after render (this might be ok if loading async)');
            } else {
                console.log('[ROUTER] Container has content, length:', this.container.innerHTML.length);
            }
        } catch (error) {
            console.error(`[ROUTER] Render error for ${mode}/${page}:`, error);
            this.showFallback();
        }
    },
    
    // Fallback-контент при ошибке
    showFallback() {
        if (!this.container) return;
        
        this.container.innerHTML = `
            <div class="stub-card">
                <h2 class="stub-title">⚠️ Ошибка загрузки</h2>
                <p class="stub-text">Не удалось загрузить страницу. Пожалуйста, попробуйте позже.</p>
            </div>
        `;
    },
    
    // Получение списка страниц для текущего режима (для navbar)
    getPagesForCurrentMode() {
        const mode = AppState.getMode();
        return Object.keys(this.routes[mode] || {});
    },
    
    // Получение конфигурации navbar для текущего режима
    getNavbarConfig() {
        const mode = AppState.getMode();
        
        if (mode === 'participant') {
            return [
                { id: 'home', label: 'Главная', icon: 'home-icon.svg' },
                { id: 'tasks', label: 'Задания', icon: 'tasks-icon.svg' },
                { id: 'giveaways', label: 'Розыгрыши', icon: 'giveaway-icon.svg' },
                { id: 'profile', label: 'Профиль', icon: 'profile-icon.svg' }
            ];
        } else { // creator
            return [
                { id: 'home', label: 'Главная', icon: 'home-icon.svg' },
                { id: 'services', label: 'Сервисы', icon: 'services-icon.svg' },
                { id: 'giveaways', label: 'Розыгрыши', icon: 'giveaway-icon.svg' },
                { id: 'stats', label: 'Статистика', icon: 'stats-icon.svg' }
            ];
        }
    }
};

// Экспортируем singleton
export default Router;
