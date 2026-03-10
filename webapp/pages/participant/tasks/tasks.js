// webapp/pages/participant/tasks/tasks.js
import { tasksListTemplate, taskDetailTemplate } from './tasks.template.js';

// ── Утилиты ───────────────────────────────────────────────────────────────
function getInitData() {
    const fromSession = sessionStorage.getItem('prizeme_init_data');
    if (fromSession) return fromSession;
    return window.Telegram?.WebApp?.initData || '';
}

function _showBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try {
        tg.BackButton.hide();
        tg.BackButton.onClick(onBack);
        tg.BackButton.show();
    } catch (e) {}
}

function _hideBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.offClick(onBack); tg.BackButton.hide(); } catch (e) {}
}

// ── Состояние ─────────────────────────────────────────────────────────────
let _currentGiveawayId   = null;
let _currentTasks        = [];
let _completedIds        = new Set();
let _backFromDetailHandler = null;

// ── Форматирование таймера ────────────────────────────────────────────────
function _formatCountdown(endUtc) {
    const now  = Date.now();
    const end  = new Date(endUtc).getTime();
    let   diff = Math.max(0, Math.floor((end - now) / 1000));
    const days  = Math.floor(diff / 86400); diff -= days * 86400;
    const hours = Math.floor(diff / 3600);  diff -= hours * 3600;
    const mins  = Math.floor(diff / 60);
    const secs  = diff - mins * 60;
    const pad = n => String(n).padStart(2, '0');
    return days > 0
        ? `${days} дн., ${pad(hours)}:${pad(mins)}:${pad(secs)}`
        : `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
}

// ── Экран 1: список розыгрышей ─────────────────────────────────────────────
async function _loadGiveaways() {
    const listEl = document.getElementById('pt-giveaway-list');
    if (!listEl) return;

    try {
        const resp = await fetch('/api/participant_task_giveaways', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ init_data: getInitData() }),
        });
        const data = await resp.json();

        if (!data.ok || !data.items.length) {
            listEl.innerHTML = `
                <div class="pt-empty">
                    <div class="pt-empty-icon">📋</div>
                    <div class="pt-empty-title">Нет активных заданий</div>
                    <div class="pt-empty-text">Примите участие в розыгрышах, чтобы выполнять задания и получать дополнительные билеты</div>
                </div>`;
            return;
        }

        listEl.innerHTML = data.items.map(g => {
            const avatarUrl    = g.first_channel_avatar_url || '/miniapp-static/uploads/avatars/default_channel.png';
            const channels     = (g.channels || []).join(', ') || '—';
            const total        = g.task_count || 0;
            const completed    = g.completed_count || 0;
            const pct          = total > 0 ? Math.round(completed / total * 100) : 0;
            return `
                <article class="participant-giveaways-card pt-giveaway-card"
                         data-giveaway-id="${g.id}"
                         data-giveaway-title="${g.title}"
                         role="button" tabindex="0">
                    <div class="participant-giveaways-card__left">
                        <div class="participant-giveaways-card__avatar">
                            <img src="${avatarUrl}" alt="" loading="lazy" />
                        </div>
                    </div>
                    <div class="participant-giveaways-card__body">
                        <div class="participant-giveaways-card__channels">${channels}</div>
                        <div class="participant-giveaways-card__title">${g.title}</div>
                        <div class="pt-card-progress">
                            <div class="pt-card-progress-bar">
                                <div class="pt-card-progress-fill" style="width:${pct}%"></div>
                            </div>
                            <span class="pt-card-progress-text">${completed}/${total}</span>
                        </div>
                    </div>
                    <div class="participant-giveaways-card__right">
                        <div class="participant-giveaways-card__arrow">
                            <img src="/miniapp-static/assets/icons/arrow-icon.svg" alt="" />
                        </div>
                    </div>
                </article>
            `;
        }).join('');

        listEl.querySelectorAll('.pt-giveaway-card').forEach(card => {
            card.addEventListener('click', () => {
                const gid   = Number(card.dataset.giveawayId);
                const title = card.dataset.giveawayTitle || '';
                _openDetail(gid, title);
            });
        });

    } catch (e) {
        listEl.innerHTML = `<div class="pt-empty"><div class="pt-empty-text">Ошибка загрузки. Попробуйте ещё раз.</div></div>`;
        console.error('[TASKS] loadGiveaways error:', e);
    }
}

// ── Экран 2: задания розыгрыша ────────────────────────────────────────────
async function _openDetail(giveawayId, giveawayTitle) {
    _currentGiveawayId = giveawayId;

    // Создаём оверлей модалки
    const overlay = document.createElement('div');
    overlay.className = 'pt-modal-overlay';
    overlay.id = 'pt-modal-overlay';
    overlay.innerHTML = `<div class="pt-modal-sheet" id="pt-modal-sheet">
        <div class="pt-modal-header">
            <div class="pt-modal-title">${giveawayTitle}</div>
            <button class="pt-modal-close" id="pt-modal-close" type="button">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
                </svg>
            </button>
        </div>
        <div class="pt-modal-body" id="pt-modal-body">
            <div class="pt-loading">Загрузка заданий...</div>
        </div>
    </div>`;
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('is-visible'));

    // Закрытие по крестику
    document.getElementById('pt-modal-close').addEventListener('click', () => _closeModal());

    // Загружаем данные
    try {
        const resp = await fetch('/api/participant_tasks', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ init_data: getInitData(), giveaway_id: giveawayId }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason);

        _currentTasks  = data.tasks || [];
        _completedIds  = new Set((data.completed_task_ids || []).map(Number));
        const rewardClaimed = !!data.reward_claimed;

        document.getElementById('pt-modal-body').innerHTML = taskDetailTemplate({
            giveawayTitle,
            tasks:        _currentTasks,
            completedIds: _completedIds,
            rewardClaimed,
        });

        _initDetailBindings(giveawayTitle);

    } catch (e) {
        document.getElementById('pt-modal-body').innerHTML =
            `<div class="pt-empty"><div class="pt-empty-text">Ошибка загрузки заданий.</div></div>`;
        console.error('[TASKS] openDetail error:', e);
    }
}

function _closeModal() {
    const overlay = document.getElementById('pt-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('is-visible');
    overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
    _loadGiveaways(); // обновляем список после закрытия
}

// ── Привязка событий на экране заданий ────────────────────────────────────
function _initDetailBindings(giveawayTitle) {
    // Кнопки «Начать»
    document.querySelectorAll('.pt-task-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const taskId     = Number(btn.dataset.taskId);
            const link       = btn.dataset.taskLink;
            const hasSecret  = btn.dataset.secret === '1';

            // Открываем ссылку если есть
            if (link) {
                const tg = window.Telegram?.WebApp;
                if (tg?.openLink) tg.openLink(link);
                else window.open(link, '_blank');
            }

            if (hasSecret) {
                // Показываем поле ввода секретного кода
                const secretBlock = document.getElementById(`pt-secret-${taskId}`);
                if (secretBlock) {
                    secretBlock.classList.remove('pt-secret-block--hidden');
                    document.getElementById(`pt-secret-input-${taskId}`)?.focus();
                }
            } else {
                // Без секретного кода — сразу отмечаем выполненным
                _completeTask(taskId, null, giveawayTitle);
            }
        });
    });

    // Кнопки подтверждения секретного кода
    document.querySelectorAll('.pt-secret-submit').forEach(btn => {
        btn.addEventListener('click', () => {
            const taskId = Number(btn.dataset.taskId);
            const input  = document.getElementById(`pt-secret-input-${taskId}`);
            const code   = (input?.value || '').trim();
            if (!code) {
                input?.classList.add('pt-secret-input--error');
                return;
            }
            _completeTask(taskId, code, giveawayTitle);
        });
    });

    // Enter в поле секрета
    document.querySelectorAll('.pt-secret-input').forEach(input => {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
                const taskId = Number(input.id.replace('pt-secret-input-', ''));
                const code   = input.value.trim();
                if (code) _completeTask(taskId, code, giveawayTitle);
            }
        });
    });

    // Кнопка «Забрать награду»
    document.getElementById('pt-claim-btn')?.addEventListener('click', () => {
        _claimReward();
    });
}

// ── Выполнение задания ────────────────────────────────────────────────────
async function _completeTask(taskId, secretCode, giveawayTitle) {
    const btn = document.querySelector(`.pt-task-btn[data-task-id="${taskId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '...'; }

    try {
        const resp = await fetch('/api/complete_task', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   getInitData(),
                task_id:     taskId,
                giveaway_id: _currentGiveawayId,
                secret_code: secretCode || null,
            }),
        });
        const data = await resp.json();

        if (!data.ok) {
            if (data.reason === 'wrong_secret') {
                const input = document.getElementById(`pt-secret-input-${taskId}`);
                if (input) {
                    input.classList.add('pt-secret-input--error');
                    input.placeholder = 'Неверный код, попробуйте ещё раз';
                    input.value = '';
                }
            }
            if (btn) { btn.disabled = false; btn.textContent = 'Начать'; }
            return;
        }

        // Успех — обновляем UI
        _completedIds.add(taskId);
        _refreshDetailUI(giveawayTitle);

    } catch (e) {
        console.error('[TASKS] completeTask error:', e);
        if (btn) { btn.disabled = false; btn.textContent = 'Начать'; }
    }
}

// ── Обновление UI после выполнения задания ────────────────────────────────
function _refreshDetailUI(giveawayTitle) {
    const body = document.getElementById('pt-modal-body');
    if (!body) return;

    body.innerHTML = taskDetailTemplate({
        giveawayTitle,
        tasks:        _currentTasks,
        completedIds: _completedIds,
        rewardClaimed: false,
    });

    _initDetailBindings(giveawayTitle);
}

// ── Получение награды ─────────────────────────────────────────────────────
async function _claimReward() {
    const btn = document.getElementById('pt-claim-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Загрузка...'; }

    try {
        const resp = await fetch('/api/claim_task_reward', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   getInitData(),
                giveaway_id: _currentGiveawayId,
            }),
        });
        const data = await resp.json();

        if (!data.ok) {
            if (btn) { btn.disabled = false; btn.textContent = '🎉 Забрать награду'; }
            return;
        }

        // Показываем модалку успеха
        _showRewardModal(data.tickets_added || 0);

    } catch (e) {
        console.error('[TASKS] claimReward error:', e);
        if (btn) { btn.disabled = false; btn.textContent = '🎉 Забрать награду'; }
    }
}

// ── Модалка награды ───────────────────────────────────────────────────────
function _showRewardModal(ticketsAdded) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🎉 Награда получена!</p>
            <p class="svc-wip-text">Вам начислено <b>+${ticketsAdded}</b> дополнительных билетов в розыгрыше.</p>
            <button class="svc-wip-btn" type="button" id="pt-reward-close">Отлично!</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));

    document.getElementById('pt-reward-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => {
            modal.remove();
            _closeModal();
        }, { once: true });
    });
}

// ── Публичный рендер ──────────────────────────────────────────────────────
function renderTasksPage() {
    const tg = window.Telegram?.WebApp;
    if (tg?.BackButton) tg.BackButton.hide();

    _currentGiveawayId = null;
    _currentTasks      = [];
    _completedIds      = new Set();

    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = tasksListTemplate();
    _loadGiveaways();
}

export { renderTasksPage };
