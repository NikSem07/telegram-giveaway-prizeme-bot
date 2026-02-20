// webapp/pages/creator/services/services.js
import servicesTemplate from './services.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderServicesPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = servicesTemplate({ user: TelegramData.getUserContext() });

    if (window.lottie) {
        lottie.loadAnimation({
            container: document.getElementById('wip-anim-services'),
            renderer:  'svg',
            loop:      true,
            autoplay:  true,
            path:      '/miniapp-static/assets/gif/Programming-Computer.json',
        });
    }
}

export { renderServicesPage };
