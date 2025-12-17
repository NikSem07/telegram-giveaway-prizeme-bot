// webapp/pages/creator/stats/stats.js

// Контент для статистики создателя
import statsTemplate from './stats.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderStatsPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    const context = {
        user: TelegramData.getUserContext()
    };

    main.innerHTML = statsTemplate(context);
}

export { renderStatsPage };
