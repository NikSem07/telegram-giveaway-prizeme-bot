// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';
import TelegramData from '../../../shared/telegram-data.js';
import Router from '../../../shared/router.js';

export function renderCreatorHomePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Загружаем данные пользователя
    const user = TelegramData.getUserContext();
    
    // Подготавливаем контекст (можно расширить при необходимости)
    const context = { 
        user,
        stats: {} // Можно добавить статистику создателя
    };
    
    // Рендерим шаблон
    main.innerHTML = creatorHomeTemplate(context);
    
    // Навешиваем обработчики событий
    attachEventListeners(main);
}

function attachEventListeners(container) {
    // Обработчики для карточек действий
    const createBtn = container.querySelector('[data-creator-action="create"]');
    const myBtn = container.querySelector('[data-creator-action="my"]');
    const statsBtn = container.querySelector('[data-creator-action="stats"]');
    
    if (createBtn) {
        createBtn.addEventListener('click', () => {
            console.log('Creator: Create giveaway clicked');
            // В будущем: Router.navigate('giveaway-create');
        });
    }
    
    if (myBtn) {
        myBtn.addEventListener('click', () => {
            Router.navigate('giveaways');
        });
    }
    
    if (statsBtn) {
        statsBtn.addEventListener('click', () => {
            Router.navigate('stats');
        });
    }
    
    // Ненавязчиво: если у тебя где-то уже есть глобальные функции - используем их
    // (оставляем для обратной совместимости)
    if (createBtn && window.createGiveaway) {
        createBtn.addEventListener('click', window.createGiveaway);
    }
    if (myBtn && window.showMyGiveaways) {
        myBtn.addEventListener('click', window.showMyGiveaways);
    }
    if (statsBtn && window.showStatistics) {
        statsBtn.addEventListener('click', window.showStatistics);
    }
}
