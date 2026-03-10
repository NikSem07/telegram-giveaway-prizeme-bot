// webapp/pages/creator/services/task-services-checkout.js
import taskCheckoutTemplate from './task-services-checkout.template.js';
import Router from '../../../shared/router.js';

// ── Цена за одно задание (загружается с сервера, дефолт на случай ошибки) ─
let _priceTaskRub   = 199;
let _priceTaskStars = 199;

async function _loadPrices() {
    try {
        const resp = await fetch('/api/prices');
        const data = await resp.json();
        if (data.ok && data.task) {
            _priceTaskRub   = data.task.rub;
            _priceTaskStars = data.task.stars;
        }
    } catch (e) {
        console.warn('[TASK_CHECKOUT] failed to load prices, using defaults');
    }
}

// ── Состояние ─────────────────────────────────────────────────────────────
let _agreed          = false;
let _paymentMethod   = 'card';   // 'card' | 'stars'
let _selectedGiveawayId = null;
let _taskCount       = 0;
let _totalRub        = 0;
let _totalStars      = 0;
let _checkoutTimerInterval = null;
let _onPaymentSuccess = null;

// ── BackButton ────────────────────────────────────────────────────────────
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

// ── Шапка и навбар ───────────────────────────────────────────────────────
function _setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';
    if (visible) {
        document.body.classList.remove('page-checkout-services');
    } else {
        document.body.classList.add('page-checkout-services');
    }
}

// ── Таймеры обратного отсчёта ─────────────────────────────────────────────
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

function _startTimers() {
    if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
    const tick = () => {
        document.querySelectorAll('.giveaway-timer[data-end]').forEach(el => {
            const end = el.dataset.end;
            if (!end) return;
            el.textContent = _formatCountdown(end);
        });
    };
    tick();
    _checkoutTimerInterval = setInterval(tick, 1000);
}

// ── Обновление итога ──────────────────────────────────────────────────────
function _updateSummary() {
    const isStars   = _paymentMethod === 'stars';
    const total     = isStars ? `${_totalStars} ⭐` : `${_totalRub} ₽`;
    const el1 = document.getElementById('tsc-summary-price');
    const el2 = document.getElementById('tsc-summary-total');
    if (el1) el1.textContent = total;
    if (el2) el2.textContent = total;

    // Обновляем цену за задание в сводке заказа
    const perTask = document.querySelector('.tsc-price-per-task');
    if (perTask) {
        perTask.textContent = isStars
            ? `${perTask.dataset.stars} ⭐`
            : `${perTask.dataset.rub} ₽`;
    }
}

// ── Загрузка розыгрышей ───────────────────────────────────────────────────
async function _loadGiveaways() {
    const listEl = document.getElementById('tsc-giveaway-list');
    if (!listEl) return;

    try {
        const initData = window.Telegram?.WebApp?.initData || '';
        const resp = await fetch('/api/task_checkout_data', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ init_data: initData }),
        });
        const data = await resp.json();

        if (!data.ok || !data.items.length) {
            listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Нет активных розыгрышей для подключения заданий</p></div>`;
            return;
        }

        listEl.innerHTML = data.items.map(g => {
            const channels  = (g.channels || []).join(', ') || '—';
            const avatarUrl = g.first_channel_avatar_url || null;
            const timerId   = `tsc-timer-${g.id}`;
            const endDate   = g.end_at_utc || null;
            return `
                <div class="tc-giveaway-card giveaway-card giveaway-card--all"
                     data-giveaway-id="${g.id}"
                     role="button" tabindex="0">
                    <div class="giveaway-left">
                        <div class="giveaway-avatar">
                            ${avatarUrl ? `<img src="${avatarUrl}" alt="" loading="lazy">` : ''}
                        </div>
                    </div>
                    <div class="giveaway-info">
                        <div class="giveaway-title">${g.title}</div>
                        <div class="giveaway-desc">${channels}</div>
                        <div class="giveaway-timer" id="${timerId}" data-end="${endDate}">—</div>
                    </div>
                    <div class="tc-giveaway-check" id="tsc-check-${g.id}">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
                        </svg>
                    </div>
                </div>
            `;
        }).join('');

        listEl.addEventListener('click', (e) => {
            const card = e.target.closest('.tc-giveaway-card');
            if (!card) return;
            _onGiveawaySelected(card);
        });

        _startTimers();

    } catch (e) {
        listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Ошибка загрузки. Попробуйте ещё раз.</p></div>`;
        console.error('[TASK_CHECKOUT] loadGiveaways error:', e);
    }
}

// ── Выбор розыгрыша ───────────────────────────────────────────────────────
function _onGiveawaySelected(card) {
    // Сбрасываем все карточки
    document.querySelectorAll('.tc-giveaway-card').forEach(c => {
        c.classList.remove('tc-giveaway-card--active');
        const checkEl = c.querySelector('.tc-giveaway-check');
        if (checkEl) checkEl.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
            </svg>`;
    });

    // Активируем выбранную
    card.classList.add('tc-giveaway-card--active');
    _selectedGiveawayId = card.dataset.giveawayId || null;

    const checkEl = card.querySelector('.tc-giveaway-check');
    if (checkEl) checkEl.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#007AFF"/>
            <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;

    // Показываем секции оплаты и итога
    document.getElementById('tsc-payment-section').classList.remove('tc-section--hidden');
    document.getElementById('tsc-summary-section').classList.remove('tc-section--hidden');
    document.getElementById('tsc-disclaimer').classList.remove('tc-section--hidden');

    const footer = document.getElementById('tsc-footer-pay');
    footer.classList.remove('tc-footer--hidden');
    footer.classList.add('is-visible');

    _updateSummary();

    // Скроллим к разделу оплаты
    document.getElementById('tsc-payment-section')
        .scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Выбор метода оплаты ───────────────────────────────────────────────────
function _initPaymentSelection() {
    document.querySelectorAll('.tc-payment-card').forEach(card => {
        card.addEventListener('click', () => {
            const method   = card.dataset.payment;
            _paymentMethod = method;

            document.querySelectorAll('.tc-payment-card').forEach(c => {
                const isActive = c.dataset.payment === method;
                c.classList.toggle('tc-payment-card--active', isActive);
                const checkEl = c.querySelector('.tc-payment-check');
                if (!checkEl) return;
                checkEl.innerHTML = isActive
                    ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                           <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                           <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                                 stroke-linecap="round" stroke-linejoin="round"/>
                       </svg>`
                    : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                           <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
                       </svg>`;
            });

            _updateSummary();
        });
    });
}

// ── Согласие с офертой ────────────────────────────────────────────────────
function _initAgreeBlock() {
    const block    = document.getElementById('tsc-agree-block');
    const checkbox = document.getElementById('tsc-agree-checkbox');
    const checkSvg = document.getElementById('tsc-agree-check');
    const payBtn   = document.getElementById('tsc-pay-btn');
    if (!block) return;

    block.addEventListener('click', (e) => {
        if (e.target.closest('[data-tg-link]')) return;
        _agreed = !_agreed;
        checkbox.classList.toggle('tc-agree-checkbox--checked', _agreed);
        checkSvg.style.display = _agreed ? 'block' : 'none';
        payBtn.classList.toggle('tc-pay-btn--inactive', !_agreed);
        if (_agreed) block.classList.remove('tc-agree-block--error');
    });
}

// ── Ссылки оферты ─────────────────────────────────────────────────────────
function _initLegalLinks() {
    document.querySelectorAll('[data-tg-link]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
            const tg = window.Telegram?.WebApp;
            if (tg?.openLink) {
                tg.openLink(link.href, { try_instant_view: true });
            } else {
                window.open(link.href, '_blank');
            }
        });
    });

    document.querySelectorAll('[data-tg-support]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
            const tg = window.Telegram?.WebApp;
            if (tg?.openTelegramLink) {
                tg.openTelegramLink(link.href);
            } else {
                window.open(link.href, '_blank');
            }
        });
    });
}

// ── Оплата Stars ──────────────────────────────────────────────────────────
async function _initiateStarsPayment() {
    const payBtn = document.getElementById('tsc-pay-btn');
    payBtn.disabled = true;
    payBtn.textContent = 'Создаём счёт...';

    try {
        const initData = window.Telegram?.WebApp?.initData || '';
        const session  = JSON.parse(sessionStorage.getItem('prizeme_task_pool') || '{}');

        const resp = await fetch('/api/task_create_stars_invoice', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   initData,
                giveaway_id: _selectedGiveawayId,
                stars:       _totalStars,
                task_pool:   session,
            }),
        });

        const data = await resp.json();
        if (!data.ok || !data.invoice_link) {
            throw new Error(data.reason || 'Не удалось создать счёт');
        }

        window.Telegram.WebApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                _showSuccessModal();
            } else if (status === 'cancelled') {
                payBtn.disabled  = false;
                payBtn.textContent = 'Перейти к оплате';
            } else if (status === 'failed') {
                _showErrorModal();
            }
        });

    } catch (e) {
        console.error('[TASK_CHECKOUT] initiateStarsPayment error:', e);
        _showErrorModal(e.message);
    } finally {
        payBtn.disabled  = false;
        payBtn.textContent = 'Перейти к оплате';
    }
}

// ── Оплата картой (Robokassa) ─────────────────────────────────────────────
async function _initiateCardPayment() {
    const payBtn = document.getElementById('tsc-pay-btn');
    payBtn.disabled = true;
    payBtn.textContent = 'Загрузка...';

    try {
        const initData = window.Telegram?.WebApp?.initData || '';
        const session  = JSON.parse(sessionStorage.getItem('prizeme_task_pool') || '{}');

        const resp = await fetch('/api/task_create_robokassa_invoice', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   initData,
                giveaway_id: _selectedGiveawayId,
                price_rub:   _totalRub,
                task_pool:   session,
            }),
        });

        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason || 'Не удалось создать счёт');

        const tg      = window.Telegram?.WebApp;
        const deepLink = `https://t.me/prizeme_official_bot?start=pay_TASK_${data.inv_id}`;

        if (tg?.openTelegramLink) {
            tg.openTelegramLink(deepLink);
        } else {
            window.open(deepLink, '_blank');
        }

        payBtn.disabled    = false;
        payBtn.textContent = 'Перейти к оплате';
        payBtn.style.background = '';
        payBtn.style.color      = '';

    } catch (e) {
        console.error('[TASK_CHECKOUT] initiateCardPayment error:', e);
        payBtn.disabled    = false;
        payBtn.textContent = 'Перейти к оплате';
        _showErrorModal(e.message);
    }
}

// ── Модалка успеха ────────────────────────────────────────────────────────
function _showSuccessModal() {
    // Чистим sessionStorage — пулл успешно оплачен
    sessionStorage.removeItem('prizeme_task_pool');

    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🎉 Оплата прошла!</p>
            <p class="svc-wip-text">Задания подключены к розыгрышу. Участники уже могут их видеть.</p>
            <button class="svc-wip-btn" type="button" id="tsc-success-close">Отлично!</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));

    document.getElementById('tsc-success-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => {
            modal.remove();
            if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
            _setShellVisibility(true);
            if (typeof _onPaymentSuccess === 'function') {
                _onPaymentSuccess();
            }
        }, { once: true });
    });
}

// ── Модалка ошибки ────────────────────────────────────────────────────────
function _showErrorModal(reason) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">❌ Ошибка оплаты</p>
            <p class="svc-wip-text">${reason || 'Не удалось провести оплату. Попробуйте ещё раз.'}</p>
            <button class="svc-wip-btn" type="button" id="tsc-error-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    document.getElementById('tsc-error-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    });
}

// ── Публичный рендер ──────────────────────────────────────────────────────
export async function renderTaskServicesCheckoutPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Читаем состояние из sessionStorage
    let session = {};
    try {
        session = JSON.parse(sessionStorage.getItem('prizeme_task_pool') || '{}');
    } catch (_) {}

    _agreed        = false;
    _paymentMethod = 'card';
    _selectedGiveawayId = null;
    if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);

    _setShellVisibility(false);
    window.scrollTo({ top: 0, behavior: 'auto' });

    // Загружаем цены с сервера прежде чем рендерить
    await _loadPrices();

    _taskCount  = (session.tasks || []).length;
    _totalRub   = _taskCount * _priceTaskRub;
    _totalStars = _taskCount * _priceTaskStars;

    const description = session.description || '';

    _setShellVisibility(false);
    window.scrollTo({ top: 0, behavior: 'auto' });

    main.innerHTML = taskCheckoutTemplate({
        taskCount:   _taskCount,
        description,
        priceRub:    _priceTaskRub,
        priceStars:  _priceTaskStars,
    });

    // BackButton → возврат на форму создания заданий
    const handleBack = () => {
        _hideBackButton(handleBack);
        if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
        Router.navigate('task_services');
    };
    _showBackButton(handleBack);

    // Callback после успешной оплаты — уходим в Сервисы
    _onPaymentSuccess = () => {
        _hideBackButton(handleBack);
        Router.navigate('services');
    };

    // Кнопка оплаты
    document.getElementById('tsc-pay-btn').addEventListener('click', () => {
        if (!_agreed) {
            const payBtn     = document.getElementById('tsc-pay-btn');
            const agreeBlock = document.getElementById('tsc-agree-block');
            agreeBlock.classList.remove('tc-agree-block--error');
            payBtn.classList.remove('tc-pay-btn--shake');
            void payBtn.offsetWidth;
            agreeBlock.classList.add('tc-agree-block--error');
            payBtn.classList.add('tc-pay-btn--shake');
            if (navigator.vibrate) navigator.vibrate(80);
            payBtn.addEventListener('animationend', () => {
                payBtn.classList.remove('tc-pay-btn--shake');
            }, { once: true });
            return;
        }

        if (!_selectedGiveawayId) return;

        if (_paymentMethod === 'stars') {
            _initiateStarsPayment();
        } else {
            _initiateCardPayment();
        }
    });

    _initPaymentSelection();
    _initAgreeBlock();
    _initLegalLinks();
    _loadGiveaways();
}
