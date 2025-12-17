// webapp/pages/participant/giveaways/giveaways.js
import giveawaysTemplate from './giveaways.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderGiveawaysPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Собираем контекст для шаблона
    const context = {
        user: TelegramData.getUserContext(),
        timestamp: new Date().toISOString()
    };

    // Рендерим через шаблон
    main.innerHTML = giveawaysTemplate(context);
}

export {
    renderGiveawaysPage,
};