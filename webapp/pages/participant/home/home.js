// webapp/pages/participant/home/home.js
import homeTemplate from './home.template.js';

// ====== Рендер страниц ======
function renderHomePage() {
    console.log('[HOME] renderHomePage called');
    
    const main = document.getElementById('main-content');
    
    if (!main) {
        console.error('[HOME] renderHomePage: main-content container not found');
        
        // Попробуем найти через альтернативные селекторы
        const fallback = document.querySelector('.main-content') || 
                        document.querySelector('main');
        
        if (!fallback) {
            console.error('[HOME] No main content container available, will retry in 100ms');
            setTimeout(renderHomePage, 100);
            return;
        }
        
        renderToContainer(fallback);
        return;
    }
    
    renderToContainer(main);
}

// Основная логика рендера
function renderToContainer(container) {
    console.log('[HOME] Rendering to container:', container);
    
    // Проверяем, что container валидный DOM элемент
    if (!container || !(container instanceof Element)) {
        console.error('[HOME] Invalid container:', container);
        return;
    }
    
    // Используем шаблон (пустой контекст, так как данные загружаются асинхронно)
    container.innerHTML = homeTemplate({});
    
    console.log('[HOME] Content rendered to container');
    
    // Загружаем данные с небольшой задержкой для гарантии
    setTimeout(() => {
        loadGiveawaysLists();
    }, 100);
}

/**
 * Возвращает HTML трёх прыгающих точек (CSS-анимация).
 * Цвет совпадает с Loading-Dots-Blue: rgb(0, 98, 219).
 * Нулевые зависимости — работает всегда и везде.
 */
function createLoadingPlaceholder() {
    return `
        <div class="loading-placeholder">
            <div class="loading-dots">
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
            </div>
        </div>
    `;
}

// ====== Загрузка розыгрышей с Node.js ======
async function loadGiveawaysLists() {
    console.log('[HOME] loadGiveawaysLists called');

    const topContainer = document.getElementById('top-giveaways-list');
    const allContainer = document.getElementById('all-giveaways-list');

    if (!topContainer || !allContainer) {
        console.warn('[HOME] Containers not found yet, retrying in 200ms');
        setTimeout(loadGiveawaysLists, 200);
        return;
    }

    topContainer.innerHTML = createLoadingPlaceholder();
    allContainer.innerHTML = createLoadingPlaceholder();

    try {
        const initData = window.Telegram?.WebApp?.initData || '';

        // Запрашиваем розыгрыши и PRIME-статус параллельно
        const [giveawaysResp, primeResp] = await Promise.all([
            fetch('/api/participant_home_giveaways', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            }),
            fetch('/api/check_prime_status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: initData })
            })
        ]);

        const data = await giveawaysResp.json();
        if (!giveawaysResp.ok || !data.ok) {
            throw new Error(data.reason || 'API error');
        }

        // PRIME-статус: если запрос упал — считаем не-PRIME (не блокируем UI)
        let isPrime = false;
        try {
            const primeData = await primeResp.json();
            isPrime = primeData.ok && primeData.is_prime === true;
        } catch (e) {
            console.warn('[HOME] prime status check failed, defaulting to non-prime');
        }

        console.log(`[HOME] is_prime=${isPrime}`);

        if (data.top && data.top.length > 0) {
            renderGiveawayList(topContainer, data.top, 'top');
        } else {
            topContainer.innerHTML = `
                <div class="top-empty">
                    <span class="top-empty-text">Пока пусто</span>
                </div>
            `;
        }

        if (isPrime) {
            // Сохраняем данные для клиентской сортировки
            _catalogData = data.latest || [];
            renderGiveawayList(allContainer, sortCatalog(_catalogData, _catalogSort), 'all');
            initCatalogFilter();
        } else {
            renderPrimeLock(allContainer, data.total_latest_count || 0);
            initCatalogFilterLocked();
        }

    } catch (err) {
        console.error('[HOME-PARTICIPANT] loadGiveawaysLists error:', err);
        topContainer.innerHTML = '<div class="giveaway-card">Не удалось загрузить розыгрыши</div>';
        allContainer.innerHTML = '';
    }
}

// ====== Pop-up: переход к розыгрышу ======

/**
 * Открывает ссылку на пост розыгрыша в Telegram.
 */
function openGiveawayPost(postUrl) {
    const tg = window.Telegram?.WebApp;
    if (!postUrl) return;
    if (tg?.openTelegramLink) {
        tg.openTelegramLink(postUrl);
    } else {
        window.open(postUrl, '_blank');
    }
}

/**
 * Показывает pop-up перехода к розыгрышу.
 * Один канал → кнопки "Отмена" / "Да".
 * Несколько каналов → список с выбором канала.
 */
function showGiveawayNavigateModal(giveaway) {
    document.getElementById('giveaway-navigate-modal')?.remove();

    const title      = escapeHtml(giveaway.title || giveaway.internal_title || 'Розыгрыш');
    const channels   = Array.isArray(giveaway.channels_meta) ? giveaway.channels_meta : [];
    const isSingle   = channels.length <= 1;

    const modal = document.createElement('div');
    modal.id        = 'giveaway-navigate-modal';
    modal.className = 'gnav-overlay';

    if (isSingle) {
        // ── Один канал / нет мета — простой pop-up ──────────────────────
        const postUrl = channels[0]?.post_url || null;
        modal.innerHTML = `
            <div class="gnav-sheet">
                <p class="gnav-question">Хотите перейти к розыгрышу?</p>
                <p class="gnav-name">${title}</p>
                <div class="gnav-actions">
                    <button class="gnav-btn gnav-btn--cancel" type="button">Отмена</button>
                    <button class="gnav-btn gnav-btn--confirm ${!postUrl ? 'gnav-btn--disabled' : ''}"
                            type="button">${postUrl ? 'Да' : 'Нет ссылки'}</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('is-visible'));

        const close = () => {
            modal.classList.remove('is-visible');
            modal.addEventListener('transitionend', () => modal.remove(), { once: true });
        };

        modal.querySelector('.gnav-btn--cancel').addEventListener('click', close);
        modal.addEventListener('click', e => { if (e.target === modal) close(); });

        if (postUrl) {
            modal.querySelector('.gnav-btn--confirm').addEventListener('click', () => {
                close();
                openGiveawayPost(postUrl);
            });
        }

    } else {
        // ── Несколько каналов — список с выбором ────────────────────────
        const channelListHtml = channels.map((ch, i) => `
            <div class="gnav-channel-card" data-index="${i}" data-post-url="${escapeHtml(ch.post_url || '')}">
                <div class="gnav-channel-avatar">
                    ${ch.avatar_url
                        ? `<img src="${escapeHtml(ch.avatar_url)}" alt="" loading="lazy">`
                        : `<div class="gnav-channel-avatar-placeholder"></div>`}
                </div>
                <span class="gnav-channel-name">${escapeHtml(ch.title || ch.username || 'Канал')}</span>
            </div>
        `).join('');

        modal.innerHTML = `
            <div class="gnav-sheet">
                <p class="gnav-question">Хотите перейти к розыгрышу?</p>
                <p class="gnav-name">${title}</p>
                <div class="gnav-channel-list">${channelListHtml}</div>
                <div class="gnav-actions gnav-actions--multi">
                    <button class="gnav-btn gnav-btn--cancel gnav-btn--cancel-narrow" type="button">Отмена</button>
                    <button class="gnav-btn gnav-btn--go gnav-btn--go-inactive" type="button" disabled>Выберите канал</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('is-visible'));

        const close = () => {
            modal.classList.remove('is-visible');
            modal.addEventListener('transitionend', () => modal.remove(), { once: true });
        };

        const cancelBtn = modal.querySelector('.gnav-btn--cancel');
        const goBtn     = modal.querySelector('.gnav-btn--go');
        let selectedUrl = null;

        // Выбор канала
        modal.querySelector('.gnav-channel-list').addEventListener('click', e => {
            const card = e.target.closest('.gnav-channel-card');
            if (!card) return;

            modal.querySelectorAll('.gnav-channel-card').forEach(c => c.classList.remove('gnav-channel-card--active'));
            card.classList.add('gnav-channel-card--active');

            selectedUrl = card.dataset.postUrl || null;

            // Активируем кнопку с анимацией
            if (selectedUrl) {
                goBtn.disabled = false;
                goBtn.classList.remove('gnav-btn--go-inactive');
                goBtn.classList.add('gnav-btn--go-active');
                goBtn.textContent = 'Перейти';

                // Анимируем кнопку "Отмена" — расширяется до равного размера
                cancelBtn.classList.add('gnav-btn--cancel-wide');
            }
        });

        cancelBtn.addEventListener('click', close);
        modal.addEventListener('click', e => { if (e.target === modal) close(); });

        goBtn.addEventListener('click', () => {
            if (!selectedUrl) return;
            close();
            openGiveawayPost(selectedUrl);
        });
    }
}

// ====== Каталог: хранение данных и состояния сортировки ======

/** Полный список розыгрышей «all», загруженный один раз. */
let _catalogData = [];

/** Текущий режим сортировки. */
let _catalogSort = 'newest';

const SORT_OPTIONS = [
    { key: 'newest',      label: 'Сначала новые' },
    { key: 'ending_soon', label: 'Скоро завершение' },
    { key: 'popular',     label: 'Самые популярные' },
    { key: 'least',       label: 'Менее популярные' },
];

/**
 * Сортирует массив розыгрышей по выбранному критерию.
 * Работает на клиенте — без повторных запросов к API.
 */
function sortCatalog(list, sortKey) {
    const copy = [...list];
    switch (sortKey) {
        case 'newest':
            // По дате публикации: новые сначала (id DESC — самый надёжный прокси)
            return copy.sort((a, b) => (b.id || 0) - (a.id || 0));
        case 'ending_soon':
            // По времени окончания: раньше заканчивается — выше
            return copy.sort((a, b) => {
                const ta = a.end_at_utc ? new Date(a.end_at_utc).getTime() : Infinity;
                const tb = b.end_at_utc ? new Date(b.end_at_utc).getTime() : Infinity;
                return ta - tb;
            });
        case 'popular':
            // По числу участников: больше — выше
            return copy.sort((a, b) => (b.participants_count || 0) - (a.participants_count || 0));
        case 'least':
            // По числу участников: меньше — выше
            return copy.sort((a, b) => (a.participants_count || 0) - (b.participants_count || 0));
        default:
            return copy;
    }
}

/**
 * Инициализирует фильтр-дропдаун для PRIME-пользователей.
 * Вся логика локальная — перерисовывает список без запроса к API.
 */
function initCatalogFilter() {
    const filterEl = document.getElementById('catalog-filter');
    const labelEl  = document.getElementById('catalog-filter-label');
    if (!filterEl || !labelEl) return;

    // Создаём выпадающее меню
    const dropdown = document.createElement('div');
    dropdown.className = 'catalog-dropdown';
    dropdown.innerHTML = SORT_OPTIONS.map(opt => `
        <button
            class="catalog-dropdown-item ${opt.key === _catalogSort ? 'is-active' : ''}"
            data-sort="${opt.key}"
            type="button"
        >${opt.label}</button>
    `).join('');
    filterEl.appendChild(dropdown);

    // Открыть / закрыть
    filterEl.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = filterEl.classList.toggle('is-open');
        dropdown.classList.toggle('is-visible', isOpen);
    });

    // Выбор пункта
    dropdown.addEventListener('click', (e) => {
        e.stopPropagation();
        const btn = e.target.closest('[data-sort]');
        if (!btn) return;

        const newSort = btn.dataset.sort;
        if (newSort === _catalogSort) {
            filterEl.classList.remove('is-open');
            dropdown.classList.remove('is-visible');
            return;
        }

        _catalogSort = newSort;
        labelEl.textContent = SORT_OPTIONS.find(o => o.key === newSort)?.label || '';

        // Обновляем active-класс
        dropdown.querySelectorAll('.catalog-dropdown-item').forEach(el => {
            el.classList.toggle('is-active', el.dataset.sort === newSort);
        });

        filterEl.classList.remove('is-open');
        dropdown.classList.remove('is-visible');

        // Перерисовываем список без запроса к API
        const allContainer = document.getElementById('all-giveaways-list');
        if (allContainer && _catalogData.length) {
            renderGiveawayList(allContainer, sortCatalog(_catalogData, _catalogSort), 'all');
        }
    });

    // Закрыть при клике вне
    document.addEventListener('click', () => {
        filterEl.classList.remove('is-open');
        dropdown.classList.remove('is-visible');
    }, { capture: false });
}

/**
 * Инициализирует заблокированный фильтр для Basic-пользователей.
 * При нажатии — анимация дёргания + вибрация.
 */
function initCatalogFilterLocked() {
    const filterEl = document.getElementById('catalog-filter');
    if (!filterEl) return;

    filterEl.classList.add('catalog-filter--locked');

    filterEl.addEventListener('click', () => {
        // Вибрация (только мобильные)
        if (navigator.vibrate) navigator.vibrate(80);

        // Анимация дёргания
        filterEl.classList.remove('catalog-filter--shaking');
        // Небольшой reflow чтобы анимация сработала повторно
        void filterEl.offsetWidth;
        filterEl.classList.add('catalog-filter--shaking');

        // Пульс на кнопке «Получить доступ»
        const btn = document.querySelector('.prime-lock-btn');
        if (btn) {
            btn.classList.remove('prime-lock-btn--pulse');
            void btn.offsetWidth;
            btn.classList.add('prime-lock-btn--pulse');
        }
    });

    filterEl.addEventListener('animationend', () => {
        filterEl.classList.remove('catalog-filter--shaking');
    });
}

// ====== Заглушка для Basic-пользователей ======
function renderPrimeLock(container, totalCount) {
    const countLabel = totalCount > 0 ? totalCount : '';
    const titleText  = countLabel ? `Доступ к ${countLabel} розыгрышам для PRIME` : 'Доступ к розыгрышам для PRIME';

    container.innerHTML = `
        <div class="prime-lock-block">
            <!-- Фоновое изображение -->
            <img
                class="prime-lock-hero-img"
                src="/miniapp-static/assets/images/giveaway-catalog.webp"
                alt=""
                draggable="false"
            />

            <!-- Градиент поверх изображения -->
            <div class="prime-lock-hero-gradient"></div>

            <!-- Контент поверх изображения -->
            <div class="prime-lock-content">
                <div class="prime-lock-text">
                    <span class="prime-lock-title">${titleText}</span>
                    <span class="prime-lock-desc">Получите доступ ко всему каталогу розыгрышей PrizeMe</span>
                </div>
                <button class="prime-lock-btn" type="button" id="prime-lock-cta">
                    <span class="prime-lock-btn-sheen"></span>
                    Получить доступ
                </button>
            </div>
        </div>
    `;

    // Обработчик кнопки — открываем Tribute
    document.getElementById('prime-lock-cta')?.addEventListener('click', () => {
        const tg = window.Telegram?.WebApp;
        if (tg && typeof tg.openTelegramLink === 'function') {
            tg.openTelegramLink('https://t.me/tribute/app?startapp=sNMT');
        } else if (tg && typeof tg.openLink === 'function') {
            tg.openLink('https://t.me/tribute/app?startapp=sNMT');
        }
    });
}


function renderGiveawayList(container, list, prefix) {
    container.innerHTML = '';

    if (!list.length) {
        container.innerHTML = '<div class="giveaway-card">Пока нет активных розыгрышей</div>';
        return;
    }

    list.forEach((g, index) => {
        const channels = Array.isArray(g.channels) ? g.channels : [];
        const channelsStr = channels.length ? channels.join(', ') : (g.title || 'Розыгрыш #' + g.id);
        const desc = stripTelegramMarkup(g.public_description || '');

        const timerId = `timer-${prefix}-${g.id}-${index}`;

        const isTop = prefix === 'top';

        // Поддержка полей из API (если есть)
        const firstChannelAvatarUrl =
            g.first_channel_avatar_url ||
            (Array.isArray(g.channels_meta) && g.channels_meta[0] && g.channels_meta[0].avatar_url) ||
            null;

        const participantsCount =
            typeof g.participants_count === 'number' ? g.participants_count :
            typeof g.members_count === 'number' ? g.members_count :
            null;

        const card = document.createElement('div');
        card.className = isTop ? 'giveaway-card giveaway-card--top' : 'giveaway-card giveaway-card--all';

        if (isTop) {
            const giveawayName = escapeHtml(g.title || g.internal_title || '');
            card.innerHTML = `
                <div class="giveaway-left">
                    <div class="giveaway-avatar giveaway-avatar--top">
                        ${firstChannelAvatarUrl ? `<img src="${escapeHtml(firstChannelAvatarUrl)}" alt="">` : ``}
                    </div>
                    <div class="giveaway-badge ${participantsCount == null ? 'giveaway-badge--hidden' : ''}">
                        <span class="giveaway-badge-icon"></span>
                        <span class="giveaway-badge-text">${participantsCount == null ? '' : formatParticipants(participantsCount)}</span>
                    </div>
                </div>
                <div class="giveaway-info">
                    <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
                    <div class="giveaway-name-fade">${giveawayName}</div>
                    <div class="giveaway-timer" id="${timerId}"></div>
                </div>
                <div class="giveaway-card-arrow">
                    <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
            `;
            // Клик по топ-карточке — тот же pop-up
            card.addEventListener('click', () => showGiveawayNavigateModal(g));
        } else {
            card.innerHTML = `
                <div class="giveaway-left">
                    <div class="giveaway-avatar giveaway-avatar--top">
                        ${firstChannelAvatarUrl ? `<img src="${escapeHtml(firstChannelAvatarUrl)}" alt="">` : ``}
                    </div>

                    <div class="giveaway-badge giveaway-badge--black ${participantsCount == null ? 'giveaway-badge--hidden' : ''}">
                        <span class="giveaway-badge-icon"></span>
                        <span class="giveaway-badge-text">${participantsCount == null ? '' : formatParticipants(participantsCount)}</span>
                    </div>
                </div>

                <div class="giveaway-info">
                    <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
                    <div class="giveaway-desc">${escapeHtml(stripTelegramMarkup(desc) || 'Описание розыгрыша')}</div>
                    <div class="giveaway-timer" id="${timerId}"></div>
                </div>

                <div class="giveaway-card-arrow">
                    <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
            `;

            // Обработчик клика — показываем pop-up
            card.addEventListener('click', () => showGiveawayNavigateModal(g));
        }

        container.appendChild(card);

        if (window.updateCountdown && g.end_at_utc) {
            // Функция updateCountdown определена в app.js
            window.updateCountdown(g.end_at_utc, timerId);
        } else if (g.end_at_utc) {
            const el = document.getElementById(timerId);
            if (el) el.textContent = 'До окончания: ' + g.end_at_utc;
        }
    });
}

function stripTelegramMarkup(input) {
    if (!input) return '';

    return String(input)
        .replace(/<\/?tg-[^>]*>/gi, '')
        .replace(/<[^>]*>/g, '')
        .replace(/&[a-z]+;/gi, '')
        .replace(/\n+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function formatParticipants(n) {
    if (typeof n !== 'number' || !isFinite(n) || n < 0) return '';

    if (n < 1000) return String(Math.floor(n));
    if (n < 100000) {
        const k = n / 1000;
        const s = k.toFixed(1).replace(/\.0$/, '');
        return `${s}к`;
    }
    if (n < 1000000) return `${Math.floor(n / 1000)}к`;

    const m = n / 1000000;
    const s = m.toFixed(2).replace(/\.00$/, '').replace(/0$/, '');
    return `${s}м`;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Экспортируем функции
export {
    renderHomePage,
    loadGiveawaysLists,
};

// Дополнительно делаем loadGiveawaysLists доступной глобально для setInterval
if (typeof window !== 'undefined') {
    window.loadGiveawaysLists = loadGiveawaysLists;
}
