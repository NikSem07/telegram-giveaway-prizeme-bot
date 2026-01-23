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

    const bg = getCssVar("--tg-overscroll-bg") || "#1C1C1C";

    try { tg.setBackgroundColor?.(bg); } catch (e) {}
    try { tg.setBottomBarColor?.(bg); } catch (e) {}
  }

  function applyTelegramBgHard() {
    // 1) сразу
    applyTelegramBg();
    // 2) и ещё раз чуть позже — чтобы перебить любые поздние setBackgroundColor
    setTimeout(applyTelegramBg, 150);
    setTimeout(applyTelegramBg, 400);
  }

  document.addEventListener("DOMContentLoaded", applyTelegramBgHard);
  window.addEventListener("load", applyTelegramBgHard);
})();
