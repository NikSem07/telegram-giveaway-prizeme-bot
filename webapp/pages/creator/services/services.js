// webapp/pages/creator/services/services.js
import servicesTemplate from './services.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderServicesPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    const context = {
        user: TelegramData.getUserContext()
    };

    main.innerHTML = servicesTemplate(context);
}

export { renderServicesPage };
