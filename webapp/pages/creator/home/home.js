// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';

export function renderCreatorHomePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Рендерим через шаблон
    main.innerHTML = creatorHomeTemplate({});
    
    // Навешиваем обработчики событий
    attachEventListeners(main);
}

function attachEventListeners(container) {
    // Обработчики для карточек действий
    container.querySelector('[data-creator-action="create"]')?.addEventListener('click', () => {
        window.createGiveaway?.();
    });
    container.querySelector('[data-creator-action="my"]')?.addEventListener('click', () => {
        window.showMyGiveaways?.();
    });
    container.querySelector('[data-creator-action="stats"]')?.addEventListener('click', () => {
        window.showStatistics?.();
    });
}