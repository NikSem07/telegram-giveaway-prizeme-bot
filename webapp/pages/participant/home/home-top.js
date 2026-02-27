// webapp/pages/participant/home/home-top.js
import homeTopTemplate from './home-top.template.js';

// ── Shell: скрыть/показать шапку и навбар ────────────────────────────────
function setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';

    if (visible) {
        document.body.classList.remove('page-home-top');
    } else {
        document.body.classList.add('page-home-top');
    }
}

// ── Telegram BackButton ───────────────────────────────────────────────────
function showBackButton(cb) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.show(); tg.BackButton.onClick(cb); } catch (e) {}
}

function hideBackButton(cb) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.offClick(cb); tg.BackButton.hide(); } catch (e) {}
}

// ── Утилиты ───────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatParticipants(n) {
    if (typeof n !== 'number' || !isFinite(n) || n < 0) return '';
    if (n < 1000) return String(Math.floor(n));
    if (n < 100000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}к`;
    if (n < 1000000) return `${Math.floor(n / 1000)}к`;
    return `${(n / 1000000).toFixed(2).replace(/\.00$/, '').replace(/0$/, '')}м`;
}

function formatCountdown(endUtc) {
    const now  = Date.now();
    const end  = new Date(endUtc).getTime();
    let   diff = Math.max(0, Math.floor((end - now) / 1000));
    const days = Math.floor(diff / 86400); diff -= days * 86400;
    const hours = Math.floor(diff / 3600); diff -= hours * 3600;
    const mins  = Math.floor(diff / 60);
    const secs  = diff - mins * 60;
    const pad   = n => String(n).padStart(2, '0');
    return days > 0
        ? `${days} дн., ${pad(hours)}:${pad(mins)}:${pad(secs)}`
        : `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
}

// ── Таймеры ───────────────────────────────────────────────────────────────
let _timerInterval = null;

function startTimers() {
    if (_timerInterval) clearInterval(_timerInterval);
    const tick = () => {
        document.querySelectorAll('.ht-card-timer[data-end]').forEach(el => {
            if (el.dataset.end) el.textContent = formatCountdown(el.dataset.end);
        });
    };
    tick();
    _timerInterval = setInterval(tick, 1000);
}

function stopTimers() {
    if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
}

// ── Загрузка данных ───────────────────────────────────────────────────────
async function loadTopGiveaways() {
    const listEl = document.getElementById('ht-list');
    if (!listEl) return;

    try {
        const resp = await fetch('/api/participant_home_giveaways', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({}),
        });
        const data = await resp.json();

        if (!data.ok || !data.top || !data.top.length) {
            listEl.innerHTML = `
                <div class="ht-empty">
                    <span class="ht-empty-icon">🏆</span>
                    <span class="ht-empty-text">Пока нет топ-розыгрышей</span>
                </div>
            `;
            return;
        }

        // Сортировка: новые (последние оплатившие) — выше
        // API уже возвращает ORDER BY tp.starts_at ASC — реверсируем
        const items = [...data.top].reverse();

        listEl.innerHTML = '';
        items.forEach(g => {
            const card = buildCard(g);
            listEl.appendChild(card);
        });

        startTimers();

    } catch (e) {
        console.error('[HOME-TOP] loadTopGiveaways error:', e);
        const listEl2 = document.getElementById('ht-list');
        if (listEl2) listEl2.innerHTML = `
            <div class="ht-empty">
                <span class="ht-empty-text">Не удалось загрузить. Попробуйте позже.</span>
            </div>
        `;
    }
}

// ── Построение карточки ───────────────────────────────────────────────────
function buildCard(g) {
    const channels      = Array.isArray(g.channels) ? g.channels : [];
    const channelsStr   = channels.length ? channels.join(', ') : (g.title || 'Розыгрыш');
    const avatarUrl     = g.first_channel_avatar_url || null;
    const participants  = typeof g.participants_count === 'number' ? g.participants_count : null;
    const giveawayName  = g.title || g.internal_title || '';

    const card = document.createElement('div');
    card.className = 'ht-card giveaway-card giveaway-card--all';
    card.innerHTML = `
        <div class="giveaway-left">
            <div class="giveaway-avatar giveaway-avatar--top">
                ${avatarUrl ? `<img src="${escapeHtml(avatarUrl)}" alt="" loading="lazy">` : ''}
            </div>
            <div class="giveaway-badge giveaway-badge--black ${participants == null ? 'giveaway-badge--hidden' : ''}">
                <span class="giveaway-badge-icon"></span>
                <span class="giveaway-badge-text">${participants != null ? formatParticipants(participants) : ''}</span>
            </div>
        </div>
        <div class="giveaway-info">
            <div class="giveaway-title">${escapeHtml(channelsStr)}</div>
            <div class="giveaway-desc">${escapeHtml(giveawayName)}</div>
            <div class="ht-card-timer" data-end="${escapeHtml(g.end_at_utc || '')}"></div>
        </div>
        <div class="giveaway-card-arrow">
            <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="1.8"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
    `;

    card.addEventListener('click', () => showNavigateModal(g));
    return card;
}

// ── Pop-up перехода (та же логика что на главной) ─────────────────────────
function openPost(postUrl) {
    const tg = window.Telegram?.WebApp;
    if (!postUrl) return;
    if (tg?.openTelegramLink) tg.openTelegramLink(postUrl);
    else window.open(postUrl, '_blank');
}

function showNavigateModal(giveaway) {
    document.getElementById('ht-navigate-modal')?.remove();

    const title    = escapeHtml(giveaway.title || giveaway.internal_title || 'Розыгрыш');
    const channels = Array.isArray(giveaway.channels_meta) ? giveaway.channels_meta : [];
    const isSingle = channels.length <= 1;

    const modal = document.createElement('div');
    modal.id        = 'ht-navigate-modal';
    modal.className = 'gnav-overlay';

    const close = () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    };

    if (isSingle) {
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

        modal.querySelector('.gnav-btn--cancel').addEventListener('click', close);
        modal.addEventListener('click', e => { if (e.target === modal) close(); });
        if (postUrl) {
            modal.querySelector('.gnav-btn--confirm').addEventListener('click', () => {
                close(); openPost(postUrl);
            });
        }
    } else {
        const channelListHtml = channels.map((ch, i) => `
            <div class="gnav-channel-card" data-index="${i}"
                 data-post-url="${escapeHtml(ch.post_url || '')}">
                <div class="gnav-channel-avatar">
                    ${ch.avatar_url
                        ? `<img src="${escapeHtml(ch.avatar_url)}" alt="" loading="lazy">`
                        : `<div class="gnav-channel-avatar-placeholder"></div>`}
                </div>
                <span class="gnav-channel-name">${escapeHtml(ch.title || 'Канал')}</span>
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

        const cancelBtn = modal.querySelector('.gnav-btn--cancel');
        const goBtn     = modal.querySelector('.gnav-btn--go');
        let selectedUrl = null;

        modal.querySelector('.gnav-channel-list').addEventListener('click', e => {
            const card = e.target.closest('.gnav-channel-card');
            if (!card) return;
            modal.querySelectorAll('.gnav-channel-card').forEach(c => c.classList.remove('gnav-channel-card--active'));
            card.classList.add('gnav-channel-card--active');
            selectedUrl = card.dataset.postUrl || null;
            if (selectedUrl) {
                goBtn.disabled = false;
                goBtn.classList.remove('gnav-btn--go-inactive');
                goBtn.classList.add('gnav-btn--go-active');
                goBtn.textContent = 'Перейти';
                cancelBtn.classList.add('gnav-btn--cancel-wide');
            }
        });

        cancelBtn.addEventListener('click', close);
        modal.addEventListener('click', e => { if (e.target === modal) close(); });
        goBtn.addEventListener('click', () => {
            if (!selectedUrl) return;
            close(); openPost(selectedUrl);
        });
    }
}

// ── Публичный API ─────────────────────────────────────────────────────────
function mountHomeTop(container, onBack) {
    stopTimers();
    container.innerHTML = homeTopTemplate();
    setShellVisibility(false);

    const handleBack = () => {
        stopTimers();
        hideBackButton(handleBack);
        setShellVisibility(true);
        onBack();
    };
    showBackButton(handleBack);

    loadTopGiveaways();
}

function unmountHomeTop() {
    stopTimers();
}

export { mountHomeTop, unmountHomeTop };
