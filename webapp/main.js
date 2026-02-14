// webapp/home_participant.js — главный экран (единый для обоих режимов)

import AppState from './shared/state.js';
import Router from './shared/router.js';
import Navbar from './shared/navbar.js';
import BackgroundManager from './shared/background-manager.js';
import { loadGiveawaysLists } from './pages/participant/home/home.js';

console.log('[HOME] Script loaded');

// Переключение режима Участник / Создатель
function switchMode(targetMode) {
  console.log('[HOME] switchMode:', targetMode);

  // текущие значения ДО переключения
  const currentMode = AppState.getMode();
  const currentPage = AppState.getPage() || 'home';

  if (targetMode === currentMode) return;

  const mapToCreator = {
    home: 'home',
    tasks: 'services',
    giveaways: 'giveaways',
    profile: 'stats'
  };

  const mapToParticipant = {
    home: 'home',
    services: 'tasks',
    giveaways: 'giveaways',
    stats: 'profile',
    giveaway_card_creator: 'giveaways'
  };

  const mappedPage =
    targetMode === 'creator'
      ? (mapToCreator[currentPage] || 'home')
      : (mapToParticipant[currentPage] || 'home');

  // ВАЖНО:
  // 1) Сначала меняем mode
  AppState.setMode(targetMode);
  syncModeSwitcherUI(targetMode);

  // 2) Потом явно ставим page, чтобы НЕ было сброса на home
  AppState.setPage(mappedPage);
}


window.switchMode = switchMode;

function syncModeSwitcherUI(mode) {
  const buttons = document.querySelectorAll('.mode-switcher .mode-btn');
  if (!buttons || !buttons.length) return;

  buttons.forEach(btn => {
    const isActive = btn.dataset.mode === mode;
    btn.classList.toggle('active', isActive);

    // если вдруг в CSS используются aria-атрибуты/доступность
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}


// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    console.log('[HOME] DOM ready');
    
    // ====== ИНИЦИАЛИЗАЦИЯ ТЕМЫ TELEGRAM ======
    const initTheme = () => {
        try {
            const tg = window.Telegram?.WebApp;
            if (tg) {
                // Определяем тему Telegram (dark/light)
                const isDark = tg.colorScheme === 'dark';
                const themeClass = isDark ? 'theme-dark' : 'theme-light';
                
                // Применяем класс к корневому элементу
                document.documentElement.classList.remove('theme-dark', 'theme-light');
                document.documentElement.classList.add(themeClass);
                
                console.log(`[THEME] Applied ${themeClass} (Telegram colorScheme: ${tg.colorScheme})`);

                // ✅ FIX: синхронизируем системный фон Telegram для СВЕТЛОЙ темы
                // (тёмную тему намеренно не трогаем)
                try {
                    if (!isDark) {
                        tg.setBackgroundColor('#EFEEF4');
                        tg.setHeaderColor('#EFEEF4');
                    }
                } catch (e) {
                    console.warn('[THEME] Failed to set Telegram colors', e);
                }
                
                // Следим за изменениями темы
                if (tg.onEvent) {
                    tg.onEvent('themeChanged', () => {
                        const newIsDark = tg.colorScheme === 'dark';
                        const newThemeClass = newIsDark ? 'theme-dark' : 'theme-light';
                        document.documentElement.classList.remove('theme-dark', 'theme-light');
                        document.documentElement.classList.add(newThemeClass);
                        console.log(`[THEME] Theme changed to ${newThemeClass}`);

                        // ✅ FIX: при смене на светлую — снова ставим нужный фон/шапку
                        try {
                            if (!newIsDark) {
                                tg.setBackgroundColor('#EFEEF4');
                                tg.setHeaderColor('#EFEEF4');
                            }
                        } catch (e) {
                            console.warn('[THEME] Failed to set Telegram colors', e);
                        }
                    });
                }
            } else {
                // Fallback: если не в Telegram, определяем по prefers-color
                const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                const themeClass = prefersDark ? 'theme-dark' : 'theme-light';
                document.documentElement.classList.remove('theme-dark', 'theme-light');
                document.documentElement.classList.add(themeClass);
                console.log(`[THEME] Fallback theme applied: ${themeClass}`);
            }
        } catch (err) {
            console.error('[THEME] initTheme error:', err);
        }
    };
    
    // 1. Инициализируем тему сразу при загрузке
    initTheme();

    // 2. Background manager (SPA only): бесшовный root фон + sync Telegram colors
    BackgroundManager.init(AppState);

    // 3. Инициализируем роутер
    Router.init();

    // ===== RESULTS -> BACK TO GIVEAWAY CARD (from finished card) =====
    try {
    const fromCard =
        sessionStorage.getItem('prizeme_force_open_card') === '1' ||
        sessionStorage.getItem('prizeme_results_from_card') === '1';

    const gid = sessionStorage.getItem('prizeme_results_back_gid');

    // чистим флаги, чтобы не было петли
    sessionStorage.removeItem('prizeme_force_open_card');
    sessionStorage.removeItem('prizeme_results_from_card');

    if (fromCard && gid) {
        console.log('[RESULTS->CARD] returning to card, gid=', gid);

        // гарантируем participant режим
        AppState.setMode('participant');

        // восстановим контекст карточки
        sessionStorage.setItem('prizeme_participant_giveaway_id', String(gid));
        sessionStorage.setItem('prizeme_participant_card_mode', 'finished');

        // ключевое: переводим SPA на карточку (используем ИМПОРТ, а не window.*)
        AppState.setPage('giveaway_card_participant');
    }
    } catch (e) {
    console.warn('[RESULTS->CARD] Failed:', e);
    }

    // 2.1 Синхронизируем UI переключалки режимов сразу после старта
    syncModeSwitcherUI(AppState.getMode());

    // 2.2 Держим UI переключалки всегда в соответствии со state
    AppState.subscribe((state) => {
        if (state.changed === 'mode') {
            syncModeSwitcherUI(state.mode);
        }
    });
    
    // 3. Навешиваем обработчики для переключателя режима
    const modeButtons = document.querySelectorAll('.mode-switcher .mode-btn');
    modeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            switchMode(btn.dataset.mode);
        });
    });
    
    // 4. Инициализируем navbar
    Navbar.init();
    
    // 5. Периодическое обновление данных на главной (только для participant)
    setInterval(() => {
        const mode = AppState.getMode();
        const page = AppState.getPage();
        
        if (mode === 'participant' && page === 'home') {
            // Используем уже импортированную функцию
            if (typeof loadGiveawaysLists === 'function') {
                loadGiveawaysLists();
            }
        }
    }, 15 * 60 * 1000); // 15 минут
});
