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

        renderGiveawayList(topContainer, data.top || [], 'top');

        if (isPrime) {
            renderGiveawayList(allContainer, data.latest || [], 'all');
        } else {
            renderPrimeLock(allContainer, data.total_latest_count || 0);
        }

    } catch (err) {
        console.error('[HOME-PARTICIPANT] loadGiveawaysLists error:', err);
        topContainer.innerHTML = '<div class="giveaway-card">Не удалось загрузить розыгрыши</div>';
        allContainer.innerHTML = '';
    }
}

// ====== Заглушка для Basic-пользователей ======
function renderPrimeLock(container, totalCount) {
    const countText = totalCount > 0 ? `${totalCount} розыгрышам` : 'эксклюзивным розыгрышам';
    container.innerHTML = `
        <div class="prime-lock-block">
            <div class="prime-lock-icon">🔒</div>
            <div class="prime-lock-text">
                <span class="prime-lock-title">Доступ только для PRIME</span>
                <span class="prime-lock-desc">Получите доступ к ${countText}</span>
            </div>
            <button class="prime-lock-btn" type="button" onclick="window.Telegram?.WebApp?.openLink('https://t.me/+EsFLBqtCrkljZWQy')">
                Получить доступ
            </button>
        </div>
    `;
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
            // giveaway name (internal_title) — одна строка с fade-вправо
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
            `;
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
            `;
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
