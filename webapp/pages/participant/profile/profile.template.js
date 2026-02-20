// webapp/pages/participant/profile/profile.template.js
export default function profileTemplate(context = {}) {
    const {
        avatarUrl = '/miniapp-static/assets/icons/profile-icon.svg',
        fullName  = 'Пользователь',
        isPrime   = false,
    } = context;

    const badgeHtml = isPrime
        ? `<span class="profile-status-badge profile-status-badge--prime">
               <span class="profile-status-badge-sheen"></span>
               PRIME
           </span>`
        : `<span class="profile-status-badge profile-status-badge--basic">Basic</span>`;

    const avatarWrapClass = isPrime
        ? 'profile-avatar-wrap profile-avatar-wrap--prime'
        : 'profile-avatar-wrap profile-avatar-wrap--basic';

    return `
        <!-- Шапка профиля -->
        <div class="profile-header">
            <div class="${avatarWrapClass}">
                <img
                    id="profile-page-avatar"
                    src="${avatarUrl}"
                    alt="Аватар"
                    class="profile-avatar"
                />
            </div>
            <div class="profile-info">
                <h2 class="profile-name" id="profile-page-name">${fullName}</h2>
                ${badgeHtml}
            </div>
        </div>

        <!-- Блок 1: Поддержка и информация -->
        <div class="profile-list">
            <button class="profile-list-item" type="button" data-profile-action="support">
                <span class="profile-list-label">Поддержка</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="profile-list-item" type="button" data-profile-action="news">
                <span class="profile-list-label">PrizeMe Новости</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="profile-list-item" type="button" data-profile-action="website">
                <span class="profile-list-label">Сайт PrizeMe</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
        </div>

        <!-- Блок 2: Подписки и донат -->
        <div class="profile-list" style="margin-top: 12px;">
            <button class="profile-list-item" type="button" data-profile-action="prime">
                <span class="profile-list-label">PRIME</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="profile-list-item" type="button" data-profile-action="premium">
                <span class="profile-list-label">ПРЕМИУМ</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="profile-list-item" type="button" data-profile-action="donate">
                <span class="profile-list-label">Донат проекту</span>
                <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
                    <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
        </div>
    `;
}
