// webapp/pages/participant/tasks/tasks.js
import tasksTemplate from './tasks.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderTasksPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = tasksTemplate({ user: TelegramData.getUserContext() });

    // Запускаем Lottie-анимацию после вставки DOM
    if (window.lottie) {
        lottie.loadAnimation({
            container: document.getElementById('wip-anim-tasks'),
            renderer:  'svg',
            loop:      true,
            autoplay:  true,
            path:      '/miniapp-static/assets/gif/Programming-Computer.json',
        });
    }
}

export { renderTasksPage };
