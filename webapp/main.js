// webapp/home_participant.js — главный экран (единый для обоих режимов)

import AppState from './shared/state.js';
import Router from './shared/router.js';
import Navbar from './shared/navbar.js';
import BackgroundManager from './shared/background-manager.js';
import { loadGiveawaysLists } from './pages/participant/home/home.js';

console.log('[HOME] Script loaded');

function detectInitialThemeClass() {
  const tg = window.Telegram?.WebApp;
  if (tg?.colorScheme === 'dark') return 'theme-dark';
  if (tg?.colorScheme === 'light') return 'theme-light';

  // Outside Telegram (browser preview)
  const prefersDark =
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;

  return prefersDark ? 'theme-dark' : 'theme-light';
}

function applyThemeClass(themeClass) {
  const root = document.documentElement;
  root.classList.remove('theme-dark', 'theme-light');
  root.classList.add(themeClass);
}

// Apply ASAP to avoid first-frame wrong background (FOUC)
applyThemeClass(detectInitialThemeClass());

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

    // ===== iOS: hard-disable pinch-to-zoom (gesture events) =====
    try {
        const prevent = (e) => {
            if (e.cancelable) e.preventDefault();
        };
        document.addEventListener('gesturestart', prevent, { passive: false });
        document.addEventListener('gesturechange', prevent, { passive: false });
        document.addEventListener('gestureend', prevent, { passive: false });
    } catch (e) {
        console.warn('[iOS] gesture disable failed', e);
    }

    console.log('[HOME] DOM ready');
    
    // ====== ИНИЦИАЛИЗАЦИЯ ТЕМЫ TELEGRAM ======
    const initTheme = () => {
    try {
        const syncTelegramChromeWithCssBg = () => {
        const tg = window.Telegram?.WebApp;
        if (!tg) return;

        const bg = getComputedStyle(document.documentElement)
            .getPropertyValue('--color-bg')
            .trim();

        if (!bg) return;

        try { tg.setBackgroundColor?.(bg); } catch (e) {}
        try { tg.setBottomBarColor?.(bg); } catch (e) {}

        // iOS/Telegram: если цвет совпадает с themeParams.bg_color / secondary_bg_color — ставим key (стабильнее, как в референсе).
        const tp = tg.themeParams || {};
        const norm = (c) => String(c || '').trim().toLowerCase();

        const bgNorm = norm(bg);
        const bgKey =
        (tp.secondary_bg_color && norm(tp.secondary_bg_color) === bgNorm) ? 'secondary_bg_color' :
        (tp.bg_color && norm(tp.bg_color) === bgNorm) ? 'bg_color' :
        null;

        try { tg.setBackgroundColor?.(bgKey || bg); } catch (e) {}
        try {
        // bottom bar: если Telegram даёт bottom_bar_bg_color — предпочитаем его ключом только когда совпало
        const bottomKey =
            (tp.bottom_bar_bg_color && norm(tp.bottom_bar_bg_color) === bgNorm) ? 'bottom_bar_bg_color' :
            (bgKey || bg);
        tg.setBottomBarColor?.(bottomKey);
        } catch (e) {}

        // Header: если совпало — key, иначе hex. НЕ делаем принудительно bg_color.
        try { tg.setHeaderColor?.(bgKey || bg); } catch (e) {}
        };

        const tg = window.Telegram?.WebApp;

        if (tg) {
        const isDark = tg.colorScheme === 'dark';
        const themeClass = isDark ? 'theme-dark' : 'theme-light';

        document.documentElement.classList.remove('theme-dark', 'theme-light');
        document.documentElement.classList.add(themeClass);

        // ✅ ВАЖНО: синкаем сразу при первичном применении темы
        syncTelegramChromeWithCssBg();

        console.log(`[THEME] Applied ${themeClass} (Telegram colorScheme: ${tg.colorScheme})`);

        if (tg.onEvent) {
            tg.onEvent('themeChanged', () => {
            const newIsDark = tg.colorScheme === 'dark';
            const newThemeClass = newIsDark ? 'theme-dark' : 'theme-light';

            document.documentElement.classList.remove('theme-dark', 'theme-light');
            document.documentElement.classList.add(newThemeClass);

            syncTelegramChromeWithCssBg();

            console.log(`[THEME] Theme changed to ${newThemeClass}`);
            });
        }

        } else {
        // Fallback: если не в Telegram, определяем по prefers-color
        const prefersDark =
            window.matchMedia &&
            window.matchMedia('(prefers-color-scheme: dark)').matches;

        const themeClass = prefersDark ? 'theme-dark' : 'theme-light';
        document.documentElement.classList.remove('theme-dark', 'theme-light');
        document.documentElement.classList.add(themeClass);

        // Вне Telegram sync не нужен (tg отсутствует), но оставим лог
        console.log(`[THEME] Fallback theme applied: ${themeClass}`);
        }
    } catch (err) {
        console.error('[THEME] initTheme error:', err);
    }
    };
    
    // ===== iOS/Telegram: prevent pull-to-minimize/close by vertical swipes =====
    try {
        const tg = window.Telegram?.WebApp;
        if (tg) {
            // Ask Telegram to expand webview as much as possible
            try { tg.expand?.(); } catch (e) {}

            // Official API (new clients)
            try { tg.disableVerticalSwipes?.(); } catch (e) {}

            // Fallback flag (some clients read it)
            try { tg.isVerticalSwipesEnabled = false; } catch (e) {}
        }

        // Extra guard for iOS rubber-band at scrollY=0
        const isIOS = tg?.platform === 'ios';
        if (isIOS) {
            let startY = 0;

            document.addEventListener('touchstart', (e) => {
                if (!e.touches || e.touches.length !== 1) return;
                startY = e.touches[0].clientY;
            }, { passive: true });

            document.addEventListener('touchmove', (e) => {
                if (!e.touches || e.touches.length !== 1) return;

                const currentY = e.touches[0].clientY;
                const deltaY = currentY - startY;

                // Only when pulling down at the very top
                if (deltaY > 0 && window.scrollY <= 0) {
                    if (e.cancelable) e.preventDefault();
                }
            }, { passive: false });
        }
    } catch (e) {
        console.warn('[TG/iOS] swipe guard init failed', e);
    }

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
