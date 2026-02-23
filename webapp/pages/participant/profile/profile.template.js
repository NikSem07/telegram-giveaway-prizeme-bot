// webapp/pages/participant/profile/profile.template.js

// ====== Иконки для строк списка ======

const ICON_ARROW = `
    <svg class="profile-list-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;

const ICON_EXTERNAL = `
    <img
        class="profile-list-arrow"
        src="/miniapp-static/assets/icons/external-link.svg"
        alt=""
        aria-hidden="true"
        style="width:14px;height:14px;opacity:0.3;filter:invert(1);"
    />`;

/**
 * Строка списка с иконкой слева.
 * @param {string} action   - data-profile-action
 * @param {string} label    - текст строки
 * @param {string} iconPath - путь к webp-иконке
 * @param {string} iconEnd  - иконка справа (ICON_ARROW или ICON_EXTERNAL)
 */
function listItem(action, label, iconPath, iconEnd) {
    return `
        <button class="profile-list-item" type="button" data-profile-action="${action}">
            <img
                class="profile-list-icon"
                src="${iconPath}"
                alt=""
                aria-hidden="true"
                loading="eager"
                decoding="sync"
            />
            <span class="profile-list-label">${label}</span>
            ${iconEnd}
        </button>`;
}

// ====== Базовый путь к иконкам профиля ======
const ICONS = '/miniapp-static/assets/images';

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
                    loading="eager"
                    decoding="sync"
                />
            </div>
            <div class="profile-info">
                <h2 class="profile-name" id="profile-page-name">${fullName}</h2>
                ${badgeHtml}
            </div>
        </div>

        <!-- Блок 1: Поддержка и информация -->
        <div class="profile-list">
            ${listItem('support', 'Поддержка',      `${ICONS}/support-icon-profile.webp`, ICON_ARROW)}
            ${listItem('news',    'PrizeMe Новости', `${ICONS}/news-icon-profile.webp`,    ICON_ARROW)}
            ${listItem('website', 'Сайт PrizeMe',    `${ICONS}/web-icon-profile.webp`,     ICON_EXTERNAL)}
        </div>

        <!-- Блок 2: Подписки и донат -->
        <div class="profile-list" style="margin-top: 12px;">
            ${listItem('prime',   'PRIME',          `${ICONS}/prime-icon-profile.webp`,   ICON_ARROW)}
            ${listItem('premium', 'ПРЕМИУМ',        `${ICONS}/premium-icon-profile.webp`, ICON_ARROW)}
            ${listItem('donate',  'Донат проекту',  `${ICONS}/donate-icon-profile.webp`,  ICON_ARROW)}
        </div>

        <!-- Блок 3: Юридические документы -->
        <div class="profile-list" style="margin-top: 12px;">
            ${listItem('privacy',      'Политика конфиденциальности',   `${ICONS}/document-icon-profile.webp`, ICON_EXTERNAL)}
            ${listItem('terms',        'Пользовательское соглашение',   `${ICONS}/document-icon-profile.webp`, ICON_EXTERNAL)}
            ${listItem('offer',        'Публичная оферта',              `${ICONS}/document-icon-profile.webp`, ICON_EXTERNAL)}
            ${listItem('subscription', 'Оферта регулярных платежей',    `${ICONS}/document-icon-profile.webp`, ICON_EXTERNAL)}
        </div>
    `;
}
