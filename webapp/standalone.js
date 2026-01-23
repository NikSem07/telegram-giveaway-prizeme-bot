// webapp/standalone.js
(function () {
  function getCssVar(name) {
    try {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    } catch (e) {
      return "";
    }
  }

  function applyTelegramBg() {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    // Цвет, который будет "под" страницей при overscroll (нижняя часть градиента)
    const bg = getCssVar("--tg-overscroll-bg") || "#1C1C1C";

    try { tg.setBackgroundColor?.(bg); } catch (e) {}
    try { tg.setBottomBarColor?.(bg); } catch (e) {}
  }

  document.addEventListener("DOMContentLoaded", applyTelegramBg);
  // На всякий случай — ещё раз после ready
  window.addEventListener("load", applyTelegramBg);
})();
