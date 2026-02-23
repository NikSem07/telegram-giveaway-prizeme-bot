// webapp/pages/participant/profile/profile.js
import profileTemplate from './profile.template.js';
import TelegramData from '../../../shared/telegram-data.js';

// ====== Вспомогательная функция открытия ссылок ======
function openTelegramLink(url) {
    const tg = window.Telegram?.WebApp;
    if (tg && typeof tg.openTelegramLink === 'function') {
        tg.openTelegramLink(url);
    } else if (tg && typeof tg.openLink === 'function') {
        tg.openLink(url);
    }
}

function openExternalLink(url) {
    const tg = window.Telegram?.WebApp;
    if (tg && typeof tg.openLink === 'function') {
        tg.openLink(url, { try_instant_view: true });
    } else {
        window.open(url, '_blank');
    }
}

// ====== Навешивание обработчиков на кликабельные строки ======
function attachProfileListeners() {
    const items = document.querySelectorAll('[data-profile-action]');
    items.forEach(item => {
        item.addEventListener('click', () => {
            const action = item.dataset.profileAction;
            switch (action) {
                case 'support':
                    openTelegramLink('https://t.me/prizeme_support');
                    break;
                case 'news':
                    openTelegramLink('https://t.me/prizeme_official_news');
                    break;
                case 'website':
                    openExternalLink('https://prizeme.ru/');
                    break;
                case 'prime':
                    openTelegramLink('https://t.me/tribute/app?startapp=sNMT');
                    break;
                case 'premium':
                    openTelegramLink('https://t.me/tribute/app?startapp=sHOW');
                    break;
                case 'donate':
                    openTelegramLink('https://t.me/tribute/app?startapp=dA1o');
                    break;
                case 'privacy':
                    openExternalLink('https://prizeme.ru/legal.html?doc=privacy');
                    break;
                case 'terms':
                    openExternalLink('https://prizeme.ru/legal.html?doc=terms');
                    break;
                case 'offer':
                    openExternalLink('https://prizeme.ru/legal.html?doc=offer');
                    break;
                case 'subscription':
                    openExternalLink('https://prizeme.ru/legal.html?doc=subscription');
                    break;
            }
        });
    });
}

// ====== Основная функция рендеринга ======
async function renderProfilePage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    const user = TelegramData.getUserContext();
    const initData = window.Telegram?.WebApp?.initData || '';

    // Запрашиваем PRIME-статус
    let isPrime = false;
    try {
        const resp = await fetch('/api/check_prime_status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: initData })
        });
        const data = await resp.json();
        isPrime = data.ok && data.is_prime === true;
    } catch (e) {
        console.warn('[PROFILE] prime status check failed:', e);
    }

    main.innerHTML = profileTemplate({
        avatarUrl: user.photoUrl || '/miniapp-static/assets/icons/profile-icon.svg',
        fullName:  user.fullName  || 'Пользователь',
        isPrime,
    });

    attachProfileListeners();
}

// ====== Обновление аватара в navbar ======
function fillProfileFromTelegram() {
    try {
        const tg = window.Telegram?.WebApp;
        const user = tg?.initDataUnsafe?.user;
        if (!user) return null;

        const navAvatarEl = document.getElementById('nav-profile-avatar');
        if (navAvatarEl && user.photo_url) {
            navAvatarEl.src = user.photo_url;
        }
        return user;
    } catch (e) {
        console.warn('[PROFILE] fillProfileFromTelegram error:', e);
        return null;
    }
}

function loadProfileFromTelegram() {
    fillProfileFromTelegram();
}

export { renderProfilePage, fillProfileFromTelegram, loadProfileFromTelegram };
