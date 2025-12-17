// webapp/pages/creator/giveaways/giveaways.js
import creatorGiveawaysTemplate from './giveaways.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderGiveawaysPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    const context = {
        user: TelegramData.getUserContext()
    };

    main.innerHTML = creatorGiveawaysTemplate(context);
}

export { renderGiveawaysPage };
