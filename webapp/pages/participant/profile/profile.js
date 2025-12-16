// ====== Рендер профиля ======
function renderProfilePage() {
  window.renderProfilePage = renderProfilePage;
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">👤 Профиль</h2>
      <p class="stub-text">Здесь позже появятся настройки профиля, ваш прогресс и история участия.</p>
    </div>
  `;
}

// ====== Профиль из Telegram WebApp ======
function fillProfileFromTelegram() {
  try {
    const tg = window.Telegram && Telegram.WebApp;
    const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!user) return;

    const avatarEl = document.getElementById('nav-profile-avatar');
    if (!avatarEl) return;

    if (user.photo_url) {
      // Telegram иногда отдаёт прямой URL аватара в user.photo_url
      avatarEl.src = user.photo_url;
    } else {
      // fallback — стандартная иконка профиля
      avatarEl.src = '/miniapp-static/assets/icons/profile-icon.svg';
    }
  } catch (e) {
    console.log('[HOME-PARTICIPANT] fillProfileFromTelegram error:', e);
  }
}


export {
  renderProfilePage,
};
