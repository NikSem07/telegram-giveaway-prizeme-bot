// webapp/shared/state.js
// Централизованное хранение состояния приложения

const AppState = {
    // Текущий режим: 'participant' | 'creator'
    currentMode: 'participant',
    
    // Текущая страница (без префикса режима)
    currentPage: 'home',
    
    // Слушатели изменений состояния
    listeners: new Set(),
    
    // Инициализация
    init() {
        // Восстанавливаем из sessionStorage, если есть
        const savedMode = sessionStorage.getItem('prizeme_mode');
        if (savedMode === 'participant' || savedMode === 'creator') {
            this.currentMode = savedMode;
        }
        console.log('[STATE] Initialized, mode:', this.currentMode);
    },
    
    // Установка режима
    setMode(mode) {
        if (mode !== 'participant' && mode !== 'creator') {
            console.error('[STATE] Invalid mode:', mode);
            return;
        }
        
        if (this.currentMode === mode) return;
        
        console.log('[STATE] Mode changed:', this.currentMode, '→', mode);
        this.currentMode = mode;
        
        // Сохраняем в sessionStorage для persistence
        try {
            sessionStorage.setItem('prizeme_mode', mode);
        } catch (e) {
            console.warn('[STATE] Cannot save mode to sessionStorage:', e);
        }
        
        // Уведомляем слушателей
        this.notify('mode');
    },
    
    // Установка страницы
    setPage(page) {
        if (!page || this.currentPage === page) return;

        console.log('[STATE] setPage called with:', page);

        console.log('[STATE] Page changed:', this.currentPage, '→', page);
        this.currentPage = page;
        this.notify('page');
    },
    
    // Получение полного пути с учетом режима
    getFullPath() {
        return `${this.currentMode}/${this.currentPage}`;
    },
    
    // Получение режима
    getMode() {
        return this.currentMode;
    },
    
    // Получение страницы
    getPage() {
        return this.currentPage;
    },
    
    // Подписка на изменения
    subscribe(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    },
    
    // Уведомление слушателей
    notify(changedField) {
        this.listeners.forEach(callback => {
            try {
                callback({
                    mode: this.currentMode,
                    page: this.currentPage,
                    fullPath: this.getFullPath(),
                    changed: changedField
                });
            } catch (e) {
                console.error('[STATE] Listener error:', e);
            }
        });
    }
};

// Экспортируем singleton
export default AppState;
