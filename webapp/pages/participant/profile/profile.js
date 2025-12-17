// webapp/pages/participant/profile/profile.js
import profileTemplate from './profile.template.js';
import TelegramData from '../../../shared/telegram-data.js';

// Основная функция рендеринга страницы
function renderProfilePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Загружаем данные из Telegram
    const user = TelegramData.getUserContext();
    
    // Передаем в шаблон
    const context = { user };
    main.innerHTML = profileTemplate(context);
}

// Функция для заполнения профиля Telegram (используется в других местах)
function fillProfileFromTelegram() {
    try {
        const tg = window.Telegram && Telegram.WebApp;
        const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
        if (!user) return null;

        // Возвращаем объект пользователя для возможного использования
        return {
            firstName: user.first_name || '',
            lastName: user.last_name || '',
            username: user.username || '',
            photoUrl: user.photo_url || null
        };
    } catch (e) {
        console.log('[PROFILE] fillProfileFromTelegram error:', e);
        return null;
    }
}

// Устаревшая функция - оставляем для обратной совместимости
// Теперь данные загружаются через TelegramData и шаблон
function loadProfileFromTelegram() {
    console.warn('[PROFILE] loadProfileFromTelegram is deprecated, use TelegramData instead');
}

export {
    renderProfilePage,
    fillProfileFromTelegram,
    loadProfileFromTelegram
};

