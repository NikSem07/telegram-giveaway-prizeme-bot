// webapp/pages/participant/profile/profile.template.js
export default function profileTemplate(context = {}) {
    const { user = {} } = context;
    const { 
        fullName = 'Пользователь', 
        username = '', 
        photoUrl = null,
        firstName = '',
        lastName = ''
    } = user;
    
    // Используем условный оператор для username
    const usernameHtml = username 
        ? `<p class="profile-username" id="profile-page-username">${username}</p>`
        : '';
    
    return `
        <div class="profile-header">
            <div class="profile-avatar-container">
                <img id="profile-page-avatar" 
                     src="${photoUrl || '/miniapp-static/assets/icons/profile-icon.svg'}" 
                     alt="Аватар"
                     class="profile-avatar">
            </div>
            <h2 class="profile-name" id="profile-page-name">${fullName}</h2>
            ${usernameHtml}
        </div>
        
        <div class="stub-card">
            <h2 class="stub-title">👤 Профиль</h2>
            <p class="stub-text">Здесь позже появятся настройки профиля, ваш прогресс и история участия.</p>
        </div>
    `;
}
