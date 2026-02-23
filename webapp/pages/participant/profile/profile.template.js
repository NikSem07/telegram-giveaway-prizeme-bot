// webapp/pages/participant/profile/profile.template.js

// ====== Иконки для строк списка ======

/** Стрелка вправо — для ссылок внутри Telegram */
const ICON_ARROW = `
    <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;

/** Иконка внешней ссылки — для ссылок, открывающихся в браузере */
const ICON_EXTERNAL = `
    <img
        class="profile-list-arrow"
        src="/miniapp-static/assets/icons/external-link.svg"
        alt=""
        aria-hidden="true"
        style="width:14px;height:14px;opacity:0.3;filter:invert(1);"
    />`;

// ====== Шаблон профиля ======
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
                ${ICON_ARROW}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="news">
                <span class="profile-list-label">PrizeMe Новости</span>
                ${ICON_ARROW}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="website">
                <span class="profile-list-label">Сайт PrizeMe</span>
                ${ICON_EXTERNAL}
            </button>
        </div>

        <!-- Блок 2: Подписки и донат -->
        <div class="profile-list" style="margin-top: 12px;">
            <button class="profile-list-item" type="button" data-profile-action="prime">
                <span class="profile-list-label">PRIME</span>
                ${ICON_ARROW}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="premium">
                <span class="profile-list-label">ПРЕМИУМ</span>
                ${ICON_ARROW}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="donate">
                <span class="profile-list-label">Донат проекту</span>
                ${ICON_ARROW}
            </button>
        </div>

        <!-- Блок 3: Юридические документы -->
        <div class="profile-list" style="margin-top: 12px;">
            <button class="profile-list-item" type="button" data-profile-action="privacy">
                <span class="profile-list-label">Политика конфиденциальности</span>
                ${ICON_EXTERNAL}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="terms">
                <span class="profile-list-label">Пользовательское соглашение</span>
                ${ICON_EXTERNAL}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="offer">
                <span class="profile-list-label">Публичная оферта</span>
                ${ICON_EXTERNAL}
            </button>
            <button class="profile-list-item" type="button" data-profile-action="subscription">
                <span class="profile-list-label">Оферта регулярных платежей</span>
                ${ICON_EXTERNAL}
            </button>
        </div>
    `;
}
