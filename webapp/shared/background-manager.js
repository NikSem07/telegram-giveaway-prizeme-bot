// webapp/shared/background-manager.js
// Enterprise-safe Background Manager for SPA (no SA screens).
// 1) Single source of truth for root bg via CSS var --app-bg
// 2) Sync Telegram WebApp colors (bg + bottom bar + header)
// 3) Reacts to AppState changes + html/body class changes (MutationObserver)

function rgbToHex(rgb) {
  if (!rgb) return null;

  const s = String(rgb).trim();

  // already hex
  if (s[0] === '#') return s;

  // rgb(...) / rgba(...)
  const m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (!m) return null;

  const r = Math.max(0, Math.min(255, parseInt(m[1], 10)));
  const g = Math.max(0, Math.min(255, parseInt(m[2], 10)));
  const b = Math.max(0, Math.min(255, parseInt(m[3], 10)));

  return (
    '#' +
    [r, g, b]
      .map((n) => n.toString(16).padStart(2, '0'))
      .join('')
      .toUpperCase()
  );
}

function readCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function pickBgColor() {
  const body = document.body;
  const html = document.documentElement;

  // Participant Giveaway Card special cases:
  // Active card uses gradient, but css sets background-color to rgba(28,28,28,1) — берём его как "system bg"
  if (body.classList.contains('page-participant-giveaway-card')) {
    if (body.classList.contains('pgc-finished-win') || html.classList.contains('pgc-finished-win')) {
      return '#024B42';
    }
    if (body.classList.contains('pgc-finished-lose') || html.classList.contains('pgc-finished-lose')) {
      return '#570C07';
    }
    // active gradient fallback color
    return '#1C1C1C';
  }

  // Default: app theme bg
  const v = readCssVar('--color-bg');
  return v || '#0F1115';
}

function applyCssBg(color) {
  // Single source of truth for root
  document.documentElement.style.setProperty('--app-bg', color);
}

function syncTelegram(color) {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;

  const hex = rgbToHex(color) || color;

  // 1) WebView background — поддерживает HEX
  try {
    if (typeof tg.setBackgroundColor === 'function') tg.setBackgroundColor(hex);
  } catch (e) {}

  // 2) Bottom bar — поддерживает HEX
  try {
    if (typeof tg.setBottomBarColor === 'function') tg.setBottomBarColor(hex);
  } catch (e) {}

  // header: iOS Telegram часто не принимает hex, ожидает токен.
  // Используем bg_color — он совпадает с темой Telegram и убирает "чёрную полосу".
  try {
    if (typeof tg.setHeaderColor === 'function') tg.setHeaderColor('bg_color');
  } catch (e) {}
}

const BackgroundManager = {
  _inited: false,
  _observer: null,
  _scheduled: false,

  applyNow() {
    const bg = pickBgColor();
    applyCssBg(bg);
    syncTelegram(bg);
  },

  scheduleApply() {
    if (this._scheduled) return;
    this._scheduled = true;
    // microtask-ish: после того как Router/страница успеет проставить классы
    setTimeout(() => {
      this._scheduled = false;
      // Ensure theme class is applied to :root (variables.css uses :root.theme-light / :root.theme-dark)
      try {
        const html = document.documentElement;
        const body = document.body;
        const tg = window.Telegram?.WebApp;

        const hasRootTheme = html.classList.contains('theme-light') || html.classList.contains('theme-dark');
        if (!hasRootTheme) {
          if (body.classList.contains('theme-light')) html.classList.add('theme-light');
          if (body.classList.contains('theme-dark')) html.classList.add('theme-dark');

          // fallback to Telegram colorScheme if body also has no theme
          if (!(html.classList.contains('theme-light') || html.classList.contains('theme-dark'))) {
            const scheme = tg?.colorScheme;
            if (scheme === 'light') html.classList.add('theme-light');
            if (scheme === 'dark') html.classList.add('theme-dark');
          }
        }
      } catch (e) {}
      
      this.applyNow();
    }, 0);
  },

  init(AppState) {
    if (this._inited) return;
    this._inited = true;

    // 1) Apply once on init (after DOM is stable)
    this.scheduleApply();

    // 2) AppState subscription (mode/page changes)
    if (AppState && typeof AppState.subscribe === 'function') {
      AppState.subscribe((state) => {
        if (state && (state.changed === 'mode' || state.changed === 'page')) {
          this.scheduleApply();
        }
      });
    }

    // 3) Observe class changes on html/body (pages add/remove classes directly)
    this._observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'attributes' && m.attributeName === 'class') {
          this.scheduleApply();
          break;
        }
      }
    });

    try {
      this._observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
      this._observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    } catch (e) {}

    // 4) Telegram theme changes (rare, but safe)
    try {
      const tg = window.Telegram?.WebApp;
      tg?.onEvent?.('themeChanged', () => this.scheduleApply());
    } catch (e) {}
  }
};

export default BackgroundManager;
