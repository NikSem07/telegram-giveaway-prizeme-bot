// webapp/pages/participant/home/home.js
import homeTemplate from './home.template.js';
import TelegramData from '../../../shared/telegram-data.js';
import Router from '../../../shared/router.js';

// Статистика по умолчанию (в реальном приложении будет загружаться с сервера)
const DEFAULT_STATS = {
    activeGiveaways: 12,
    completedTasks: 5,
    wins: 2
};

function renderHomePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Загружаем данные
    const user = TelegramData.getUserContext();
    
    // В реальном приложении здесь будет загрузка статистики с сервера
    const stats = DEFAULT_STATS;
    
    // Подготавливаем контекст для шаблона
    const context = { 
        user,
        stats
    };
    
    // Рендерим шаблон
    main.innerHTML = homeTemplate(context);
    
    // Навешиваем обработчики событий
    attachEventListeners();
}

function attachEventListeners() {
    // Обработчики для быстрых действий
    document.querySelectorAll('[data-action]').forEach(button => {
        button.addEventListener('click', (e) => {
            const action = e.currentTarget.getAttribute('data-action');
            handleAction(action);
        });
    });
}

function handleAction(action) {
    switch (action) {
        case 'participate':
            Router.navigate('giveaways');
            break;
        case 'tasks':
            Router.navigate('tasks');
            break;
        case 'my-giveaways':
            Router.navigate('giveaways');
            break;
        case 'profile':
            Router.navigate('profile');
            break;
        default:
            console.log('Unknown action:', action);
    }
}

export { renderHomePage };
