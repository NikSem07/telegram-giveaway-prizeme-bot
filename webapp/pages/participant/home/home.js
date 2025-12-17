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

    topContainer.innerHTML = '<div class="giveaway-card">Загружаем топ розыгрышей…</div>';
    allContainer.innerHTML = '<div class="giveaway-card">Загружаем текущие розыгрыши…</div>';

    try {
        const resp = await fetch('/api/participant_home_giveaways', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });

        const data = await resp.json();
        if (!resp.ok || !data.ok) {
            throw new Error(data.reason || 'API error');
        }

        renderGiveawayList(topContainer, data.top || [], 'top');
        renderGiveawayList(allContainer, data.latest || [], 'all');
    } catch (err) {
        console.error('[HOME-PARTICIPANT] loadGiveawaysLists error:', err);
        topContainer.innerHTML = '<div class="giveaway-card">Не удалось загрузить розыгрыши</div>';
        allContainer.innerHTML = '';
    }
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
                    <div class="giveaway-desc">${escapeHtml(stripTelegramMarkup(desc) || 'Описание розыгрыша')}</div>
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
