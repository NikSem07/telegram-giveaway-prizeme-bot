// webapp/pages/participant/tasks/tasks.js
import tasksTemplate from './tasks.template.js';
import TelegramData from '../../../shared/telegram-data.js';

function renderTasksPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    const context = {
        user: TelegramData.getUserContext()
    };

    main.innerHTML = tasksTemplate(context);
}

export {
    renderTasksPage,
};
