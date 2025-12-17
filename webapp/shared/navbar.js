// webapp/shared/navbar.js
// Динамический navbar, зависящий от режима

import AppState from './state.js';
import Router from './router.js';

const Navbar = {
    // Контейнер navbar
    container: null,
    
    // Иконки по умолчанию (пути)
    defaultIcons: {
        'home': 'home-icon.svg',
        'tasks': 'tasks-icon.svg',
        'giveaways': 'giveaway-icon.svg',
        'profile': 'profile-icon.svg',
        'services': 'services-icon.svg',
        'stats': 'stats-icon.svg'
    },
    
    // Инициализация
    init() {
        this.container = document.querySelector('.bottom-nav');
        if (!this.container) {
            console.error('[NAVBAR] Navbar container not found');
            return;
        }
        
        console.log('[NAVBAR] Initialized');
        
        // Подписываемся на изменения режима
        AppState.subscribe((state) => {
            if (state.changed === 'mode') {
                this.render();
            }
        });
        
        // Рендерим начальный navbar
        this.render();
    },
    
    // Рендер navbar
    render() {
        const mode = AppState.getMode();
        const currentPage = AppState.getPage();
        const config = Router.getNavbarConfig();
        
        if (!this.container) return;
        
        console.log(`[NAVBAR] Rendering for mode: ${mode}`);
        
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
        
        // Активный фон
        const activeBg = document.createElement('div');
        activeBg.className = 'nav-active-bg';
        div.appendChild(activeBg);
        
        // Иконка или аватар
        if (isProfile) {
            const avatarContainer = document.createElement('div');
            avatarContainer.className = 'nav-avatar';
            
            const avatarImg = document.createElement('img');
            avatarImg.id = 'nav-profile-avatar';
            avatarImg.src = `/miniapp-static/assets/icons/${item.icon}`;
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
    
    // Обновление аватара (для профиля)
    updateAvatar(avatarUrl) {
        const avatarImg = document.getElementById('nav-profile-avatar');
        if (avatarImg && avatarUrl) {
            avatarImg.src = avatarUrl;
        }
    }
};

export default Navbar;
