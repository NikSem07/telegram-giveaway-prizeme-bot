// ====== Рендер профиля ======
function renderProfilePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="profile-header">
      <div class="profile-avatar-container">
        <img id="profile-page-avatar" 
             src="/miniapp-static/assets/icons/profile-icon.svg" 
             alt="Аватар"
             class="profile-avatar">
      </div>
      <h2 class="profile-name" id="profile-page-name">Пользователь</h2>
      <p class="profile-username" id="profile-page-username"></p>
    </div>
    
    <div class="stub-card">
      <h2 class="stub-title">👤 Профиль</h2>
      <p class="stub-text">Здесь позже появятся настройки профиля, ваш прогресс и история участия.</p>
    </div>
  `;

  // Загружаем данные из Telegram при рендере страницы
  loadProfileFromTelegram();
}

// ====== Загрузка профиля из Telegram ======
function loadProfileFromTelegram() {
  try {
    const tg = window.Telegram && Telegram.WebApp;
    const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!user) return;

    // Обновляем аватар на странице
    const avatarEl = document.getElementById('profile-page-avatar');
    if (avatarEl && user.photo_url) {
      avatarEl.src = user.photo_url;
    }

    // Обновляем имя
    const nameEl = document.getElementById('profile-page-name');
    if (nameEl && (user.first_name || user.last_name)) {
      const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
      nameEl.textContent = fullName;
    }

    // Обновляем username
    const usernameEl = document.getElementById('profile-page-username');
    if (usernameEl && user.username) {
      usernameEl.textContent = `@${user.username}`;
    }
  } catch (e) {
    console.log('[PROFILE] loadProfileFromTelegram error:', e);
  }
}

// ====== Профиль из Telegram WebApp для навбара ======
function fillProfileFromTelegram() {
  try {
    const tg = window.Telegram && Telegram.WebApp;
    const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!user) return;

    // Обновляем аватар в навбаре
    const navAvatarEl = document.getElementById('nav-profile-avatar');
    if (navAvatarEl && user.photo_url) {
      navAvatarEl.src = user.photo_url;
    }
    
    return user; // Возвращаем объект пользователя для возможного использования
  } catch (e) {
    console.log('[PROFILE] fillProfileFromTelegram error:', e);
    return null;
  }
}


export {
  renderProfilePage,
  fillProfileFromTelegram,
  loadProfileFromTelegram
};
