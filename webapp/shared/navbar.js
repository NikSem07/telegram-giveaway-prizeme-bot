// webapp/shared/navbar.js
// Динамический navbar, зависящий от режима

import AppState from './state.js';
import Router from './router.js';

const Navbar = {
    // Контейнер navbar
    container: null,
    
    // URL аватара (сохраняем между перерисовками)
    avatarUrl: null,
    
    // Инициализация
    init() {
        this.container = document.querySelector('.bottom-nav');
        if (!this.container) {
            console.error('[NAVBAR] Navbar container not found');
            return;
        }
        
        console.log('[NAVBAR] Initialized');
        
        // Пытаемся получить аватар из Telegram при инициализации
        this.loadAvatarFromTelegram();
        
        // Подписываемся на изменения режима И страницы
        AppState.subscribe((state) => {
            if (state.changed === 'mode' || state.changed === 'page') {
                this.render();
            }
        });
        
        // Рендерим начальный navbar
        this.render();
    },
    
    // Загрузка аватара из Telegram
    loadAvatarFromTelegram() {
        try {
            const tg = window.Telegram && Telegram.WebApp;
            const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
            if (user && user.photo_url) {
                this.avatarUrl = user.photo_url;
                console.log('[NAVBAR] Avatar URL loaded:', this.avatarUrl);
            }
        } catch (e) {
            console.log('[NAVBAR] Error loading avatar:', e);
        }
    },
    
    // Рендер navbar
    render() {
        const mode = AppState.getMode();
        const currentPage = AppState.getPage();
        const config = Router.getNavbarConfig();
        
        if (!this.container) return;
        
        console.log(`[NAVBAR] Rendering for mode: ${mode}, page: ${currentPage}`);
        
        // Очищаем контейнер
        this.container.innerHTML = '';
        
        // Создаем кнопки навигации
        config.forEach(item => {
            const navItem = this.createNavItem(item, currentPage);
            this.container.appendChild(navItem);
        });
        
        // Добавляем обработчики кликов
        this.attachEventListeners();
    },
    
    // Создание элемента навигации
    createNavItem(item, currentPage) {
        const isActive = item.id === currentPage;
        const isProfile = item.id === 'profile';
        
        const div = document.createElement('div');
        div.className = `nav-item ${isActive ? 'active' : ''} ${isProfile ? 'nav-profile' : ''}`;
        div.setAttribute('data-page', item.id);
        
        // Иконка или аватар
        if (isProfile) {
            const avatarContainer = document.createElement('div');
            avatarContainer.className = 'nav-avatar';
            
            const avatarImg = document.createElement('img');
            avatarImg.id = 'nav-profile-avatar';
            // ИСПРАВЛЕНО: убираем класс nav-icon, добавляем nav-avatar-img
            avatarImg.className = 'nav-avatar-img';
            
            // Используем сохраненный URL аватара или иконку по умолчанию
            avatarImg.src = this.avatarUrl || `/miniapp-static/assets/icons/${item.icon}`;
            avatarImg.alt = '';
            
            avatarContainer.appendChild(avatarImg);
            div.appendChild(avatarContainer);
        } else {
            const iconImg = document.createElement('img');
            iconImg.className = 'nav-icon';
            iconImg.src = `/miniapp-static/assets/icons/${item.icon}`;
            iconImg.alt = '';
            div.appendChild(iconImg);
        }
        
        // Подпись
        const label = document.createElement('span');
        label.className = 'nav-label';
        label.textContent = item.label;
        div.appendChild(label);
        
        return div;
    },
    
    // Прикрепление обработчиков событий
    attachEventListeners() {
        const items = this.container.querySelectorAll('.nav-item');
        
        items.forEach(item => {
            // Удаляем старые обработчики
            const newItem = item.cloneNode(true);
            item.parentNode.replaceChild(newItem, item);
            
            // Добавляем новый обработчик
            newItem.addEventListener('click', () => {
                const page = newItem.getAttribute('data-page');
                if (page) {
                    Router.navigate(page);
                }
            });
        });
    },
    
    // Обновление аватара (для внешнего использования)
    updateAvatar(avatarUrl) {
        if (avatarUrl) {
            this.avatarUrl = avatarUrl;
            
            // Обновляем аватар в DOM, если он существует
            const avatarImg = document.getElementById('nav-profile-avatar');
            if (avatarImg) {
                avatarImg.src = avatarUrl;
            }
            
            console.log('[NAVBAR] Avatar updated:', avatarUrl);
        }
    }
};

export default Navbar;
