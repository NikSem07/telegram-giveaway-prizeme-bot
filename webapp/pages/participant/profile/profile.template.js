// webapp/pages/participant/profile/profile.template.js
export default function profileTemplate(context = {}) {
    const { 
        avatarUrl = '/miniapp-static/assets/icons/profile-icon.svg',
        fullName = 'Пользователь',
        username = ''
    } = context;
    
    const usernameHtml = username 
        ? `<p class="profile-username" id="profile-page-username">${username}</p>`
        : '';
    
    return `
        <div class="profile-header">
            <div class="profile-avatar-container">
                <img id="profile-page-avatar" 
                     src="${avatarUrl}" 
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
