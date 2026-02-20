// webapp/pages/creator/stats/stats.js
import statsTemplate from './stats.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderStatsPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = statsTemplate({ user: TelegramData.getUserContext() });

    if (window.lottie) {
        lottie.loadAnimation({
            container: document.getElementById('wip-anim-stats'),
            renderer:  'svg',
            loop:      true,
            autoplay:  true,
            path:      '/miniapp-static/assets/gif/Programming-Computer.json',
        });
    }
}

export { renderStatsPage };
