// webapp/pages/participant/profile/profile.js
import profileTemplate from './profile.template.js';
import TelegramData from '../../../shared/telegram-data.js';

// Основная функция рендеринга страницы
function renderProfilePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Загружаем данные из Telegram
    const user = TelegramData.getUserContext();
    
    // Подготавливаем контекст для шаблона
    const context = {
        avatarUrl: user.photoUrl || '/miniapp-static/assets/icons/profile-icon.svg',
        fullName: user.fullName || 'Пользователь',
        username: user.username || ''
    };
    
    // Рендерим через шаблон
    main.innerHTML = profileTemplate(context);
}

// Функция для заполнения профиля Telegram (используется в других местах)
function fillProfileFromTelegram() {
    try {
        const tg = window.Telegram && Telegram.WebApp;
        const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
        if (!user) return null;

        // Обновляем аватар в навбаре
        const navAvatarEl = document.getElementById('nav-profile-avatar');
        if (navAvatarEl && user.photo_url) {
            navAvatarEl.src = user.photo_url;
        }
        
        return user; // Возвращаем объект пользователя для возможного использования
    } catch (e) {
        console.log('[PROFILE] fillProfileFromTelegram error:', e);
        return null;
    }
}

// Устаревшая функция - оставляем для обратной совместимости
function loadProfileFromTelegram() {
    try {
        const tg = window.Telegram && Telegram.WebApp;
        const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
        if (!user) return;

        // Обновляем аватар на странице
        const avatarEl = document.getElementById('profile-page-avatar');
        if (avatarEl && user.photo_url) {
            avatarEl.src = user.photo_url;
        }

        // Обновляем имя
        const nameEl = document.getElementById('profile-page-name');
        if (nameEl && (user.first_name || user.last_name)) {
            const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
            nameEl.textContent = fullName;
        }

        // Обновляем username
        const usernameEl = document.getElementById('profile-page-username');
        if (usernameEl && user.username) {
            usernameEl.textContent = `@${user.username}`;
        }
    } catch (e) {
        console.log('[PROFILE] loadProfileFromTelegram error:', e);
    }
}

export {
    renderProfilePage,
    fillProfileFromTelegram,
    loadProfileFromTelegram
};
