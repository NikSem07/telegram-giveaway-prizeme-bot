// webapp/pages/creator/services/promotion-services.js
import promotionCheckoutTemplate from './promotion-services.template.js';

// ── Цена (меняется в одном месте) ────────────────────────────────────────
const PROMOTION_PRICE_RUB   = 9990;   // ₽  ← меняй здесь
const PROMOTION_PRICE_STARS = 500;    // ⭐ ← меняй здесь

// ── Состояние чекаута ─────────────────────────────────────────────────────
let _agreed             = false;
let _paymentMethod      = 'stars';  // stars | card
let _selectedGiveawayId = null;
let _selectedTimeType   = 'immediate'; // immediate | scheduled
let _scheduledAt        = null;        // ISO string
let _checkoutTimerInterval = null;

// ── Шапка / навбар ────────────────────────────────────────────────────────
function setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';
    if (visible) {
        document.body.classList.remove('page-checkout-services');
    } else {
        document.body.classList.add('page-checkout-services');
    }
}

// ── Back Button ───────────────────────────────────────────────────────────
function showBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.show(); tg.BackButton.onClick(onBack); } catch (e) {}
}
function hideBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.offClick(onBack); tg.BackButton.hide(); } catch (e) {}
}

// ── Таймеры ───────────────────────────────────────────────────────────────
function formatCountdown(endUtc) {
    const now  = Date.now();
    const end  = new Date(endUtc).getTime();
    let   diff = Math.max(0, Math.floor((end - now) / 1000));
    const days  = Math.floor(diff / 86400); diff -= days * 86400;
    const hours = Math.floor(diff / 3600);  diff -= hours * 3600;
    const mins  = Math.floor(diff / 60);
    const secs  = diff - mins * 60;
    const pad   = n => String(n).padStart(2, '0');
    return days > 0
        ? `${days} дн., ${pad(hours)}:${pad(mins)}:${pad(secs)}`
        : `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
}

function startCheckoutTimers() {
    if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
    const tick = () => {
        document.querySelectorAll('.giveaway-timer[data-end]').forEach(el => {
            const end = el.dataset.end;
            if (end) el.textContent = formatCountdown(end);
        });
    };
    tick();
    _checkoutTimerInterval = setInterval(tick, 1000);
}

// ── Загрузка розыгрышей ───────────────────────────────────────────────────
async function loadGiveaways() {
    const listEl = document.getElementById('promo-giveaway-list');
    if (!listEl) return;

    try {
        const initData = window.Telegram?.WebApp?.initData
            || sessionStorage.getItem('prizeme_init_data') || '';
        const resp = await fetch('/api/promotion_checkout_data', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ init_data: initData }),
        });
        const data = await resp.json();

        if (!data.ok || !data.items.length) {
            listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Нет активных розыгрышей для продвижения</p></div>`;
            return;
        }

        listEl.innerHTML = data.items.map(g => {
            const channels  = (g.channels || []).join(', ') || '—';
            const avatarUrl = g.first_channel_avatar_url || null;
            const timerId   = `promo-timer-${g.id}`;
            return `
                <div class="tc-giveaway-card giveaway-card giveaway-card--all"
                     data-giveaway-id="${g.id}" role="button" tabindex="0">
                    <div class="giveaway-left">
                        <div class="giveaway-avatar">
                            ${avatarUrl ? `<img src="${avatarUrl}" alt="" loading="lazy">` : ''}
                        </div>
                    </div>
                    <div class="giveaway-info">
                        <div class="giveaway-title">${g.title}</div>
                        <div class="giveaway-desc">${channels}</div>
                        <div class="giveaway-timer" id="${timerId}" data-end="${g.end_at_utc || ''}">—</div>
                    </div>
                    <div class="tc-giveaway-check" id="promo-check-${g.id}">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
                        </svg>
                    </div>
                </div>
            `;
        }).join('');

        listEl.addEventListener('click', e => {
            const card = e.target.closest('.tc-giveaway-card');
            if (card) onGiveawaySelected(card);
        });

        startCheckoutTimers();

    } catch (e) {
        if (listEl) listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Ошибка загрузки. Попробуйте ещё раз.</p></div>`;
        console.error('[PROMO_CHECKOUT] loadGiveaways error:', e);
    }
}

// ── Выбор розыгрыша ───────────────────────────────────────────────────────
function onGiveawaySelected(card) {
    document.querySelectorAll('.tc-giveaway-card').forEach(c => {
        c.classList.remove('tc-giveaway-card--active');
        const ch = c.querySelector('.tc-giveaway-check');
        if (ch) ch.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/></svg>`;
    });

    card.classList.add('tc-giveaway-card--active');
    _selectedGiveawayId = card.dataset.giveawayId || null;

    const ch = card.querySelector('.tc-giveaway-check');
    if (ch) ch.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#007AFF"/>
            <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;

    // Показываем выбор времени
    const timeSection = document.getElementById('promo-time-section');
    timeSection.classList.remove('tc-section--hidden');
    timeSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Сбрасываем оплату
    _resetPaymentBlocks();
}

// ── Выбор времени публикации ──────────────────────────────────────────────
function initTimeSelection() {
    document.querySelectorAll('.promo-time-card').forEach(card => {
        card.addEventListener('click', () => onTimeSelected(card));
    });

    // Обработчик пикера даты
    const picker = document.getElementById('promo-datetime-input');
    if (picker) {
        // Минимальное время — сейчас + 1 час
        const minDate = new Date(Date.now() + 60 * 60 * 1000);
        picker.min = minDate.toISOString().slice(0, 16);

        picker.addEventListener('change', () => {
            if (picker.value) {
                _scheduledAt = new Date(picker.value).toISOString();
                const label = document.getElementById('promo-scheduled-desc');
                if (label) {
                    const d = new Date(picker.value);
                    label.textContent = d.toLocaleString('ru-RU', {
                        day: '2-digit', month: '2-digit', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                    }) + ' (МСК)';
                }
                // Показываем блоки оплаты
                _showPaymentBlocks();
            }
        });
    }
}

function onTimeSelected(card) {
    const timeType = card.dataset.timeType;
    _selectedTimeType = timeType;

    // Обновляем галочки
    document.querySelectorAll('.promo-time-card').forEach(c => {
        const isActive = c.dataset.timeType === timeType;
        c.classList.toggle('promo-time-card--active', isActive);
        const checkId = `promo-time-check-${c.dataset.timeType}`;
        const checkEl = document.getElementById(checkId);
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

    const pickerWrap = document.getElementById('promo-datetime-picker');

    if (timeType === 'immediate') {
        _scheduledAt = null;
        if (pickerWrap) pickerWrap.classList.add('tc-section--hidden');
        _showPaymentBlocks();
    } else {
        // scheduled — показываем пикер, оплату покажем после выбора даты
        if (pickerWrap) pickerWrap.classList.remove('tc-section--hidden');
        _resetPaymentBlocks();
        // Если дата уже была выбрана раньше
        const picker = document.getElementById('promo-datetime-input');
        if (picker && picker.value) {
            _scheduledAt = new Date(picker.value).toISOString();
            _showPaymentBlocks();
        }
    }
}

// ── Показ / сброс блоков оплаты ───────────────────────────────────────────
function _showPaymentBlocks() {
    ['promo-payment-section', 'promo-summary-section',
     'promo-agree-section', 'promo-disclaimer'].forEach(id => {
        document.getElementById(id)?.classList.remove('tc-section--hidden');
    });
    const footer = document.getElementById('promo-footer-pay');
    if (footer) {
        footer.classList.remove('tc-footer--hidden');
        footer.classList.add('is-visible');
    }
    _updateSummaryDisplay();
}

function _resetPaymentBlocks() {
    ['promo-payment-section', 'promo-summary-section',
     'promo-agree-section', 'promo-disclaimer'].forEach(id => {
        document.getElementById(id)?.classList.add('tc-section--hidden');
    });
    document.getElementById('promo-footer-pay')?.classList.add('tc-footer--hidden');
    _agreed = false;
    const checkbox = document.getElementById('promo-agree-checkbox');
    const checkSvg = document.getElementById('promo-agree-check');
    const payBtn   = document.getElementById('promo-pay-btn');
    if (checkbox) checkbox.classList.remove('tc-agree-checkbox--checked');
    if (checkSvg) checkSvg.style.display = 'none';
    if (payBtn)   payBtn.classList.add('tc-pay-btn--inactive');
}

// ── Итог ──────────────────────────────────────────────────────────────────
function _updateSummaryDisplay() {
    const isStars = _paymentMethod === 'stars';
    const text    = isStars ? `${PROMOTION_PRICE_STARS} ⭐` : `${PROMOTION_PRICE_RUB.toLocaleString('ru-RU')} ₽`;
    const priceEl = document.getElementById('promo-summary-price');
    const totalEl = document.getElementById('promo-summary-total');
    if (priceEl) priceEl.textContent = text;
    if (totalEl) totalEl.textContent = text;
}

// ── Выбор метода оплаты ───────────────────────────────────────────────────
function initPaymentSelection() {
    document.querySelectorAll('[data-payment]').forEach(card => {
        card.addEventListener('click', () => {
            const method = card.dataset.payment;
            _paymentMethod = method;

            document.querySelectorAll('[data-payment]').forEach(c => {
                const isActive = c.dataset.payment === method;
                c.classList.toggle('tc-payment-card--active', isActive);
                const checkId = `promo-pay-check-${c.dataset.payment}`;
                const checkEl = document.getElementById(checkId);
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

            _updateSummaryDisplay();
        });
    });
}

// ── Согласие с офертой ────────────────────────────────────────────────────
function initAgreeBlock() {
    const block    = document.getElementById('promo-agree-block');
    const checkbox = document.getElementById('promo-agree-checkbox');
    const checkSvg = document.getElementById('promo-agree-check');
    const payBtn   = document.getElementById('promo-pay-btn');
    if (!block) return;

    block.addEventListener('click', e => {
        if (e.target.closest('[data-tg-link]')) return;
        _agreed = !_agreed;
        checkbox.classList.toggle('tc-agree-checkbox--checked', _agreed);
        checkSvg.style.display = _agreed ? 'block' : 'none';
        payBtn.classList.toggle('tc-pay-btn--inactive', !_agreed);
        if (_agreed) block.classList.remove('tc-agree-block--error');
    });
}

// ── Ссылки оферты ─────────────────────────────────────────────────────────
function initLegalLinks() {
    document.querySelectorAll('[data-tg-link]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault(); e.stopPropagation();
            const tg = window.Telegram?.WebApp;
            tg?.openLink ? tg.openLink(link.href, { try_instant_view: true })
                         : window.open(link.href, '_blank');
        });
    });
    document.querySelectorAll('[data-tg-support]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault(); e.stopPropagation();
            const tg = window.Telegram?.WebApp;
            tg?.openTelegramLink ? tg.openTelegramLink(link.href)
                                 : window.open(link.href, '_blank');
        });
    });
}

// ── Оплата Stars ──────────────────────────────────────────────────────────
async function initiateStarsPayment() {
    const payBtn = document.getElementById('promo-pay-btn');
    payBtn.disabled = true;
    payBtn.textContent = 'Создаём счёт...';

    try {
        const initData = window.Telegram?.WebApp?.initData
            || sessionStorage.getItem('prizeme_init_data') || '';

        const resp = await fetch('/api/create_promotion_stars_invoice', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:    initData,
                giveaway_id:  _selectedGiveawayId,
                publish_type: _selectedTimeType,
                scheduled_at: _scheduledAt,
            }),
        });
        const data = await resp.json();

        if (!data.ok || !data.invoice_link)
            throw new Error(data.reason || 'Не удалось создать счёт');

        window.Telegram.WebApp.openInvoice(data.invoice_link, status => {
            if (status === 'paid') {
                showPaymentSuccessModal();
            } else if (status === 'cancelled') {
                payBtn.disabled = false;
                payBtn.textContent = 'Перейти к оплате';
            } else if (status === 'failed') {
                showPaymentErrorModal();
            }
        });
    } catch (e) {
        console.error('[PROMO_CHECKOUT] initiateStarsPayment error:', e);
        showPaymentErrorModal(e.message);
    } finally {
        payBtn.disabled = false;
        payBtn.textContent = 'Перейти к оплате';
    }
}

// ── Оплата картой — заглушка ──────────────────────────────────────────────
function initiateCardPayment() {
    _showWipModal('🚧 В разработке', 'Оплата картой скоро будет доступна. Используйте Telegram Stars.');
}

// ── Модальные окна ────────────────────────────────────────────────────────
let _onPaymentSuccess = null;

function showPaymentSuccessModal() {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🎉 Заявка принята!</p>
            <p class="svc-wip-text">Ваш розыгрыш будет опубликован в боте после утверждения администратором (до 8 часов).</p>
            <button class="svc-wip-btn" type="button" id="promo-success-close">Отлично!</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    document.getElementById('promo-success-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => {
            modal.remove();
            setShellVisibility(true);
            if (typeof _onPaymentSuccess === 'function') _onPaymentSuccess();
        }, { once: true });
    });
}

function showPaymentErrorModal(reason) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">❌ Ошибка оплаты</p>
            <p class="svc-wip-text">${reason || 'Не удалось провести оплату. Попробуйте ещё раз.'}</p>
            <button class="svc-wip-btn" type="button" id="promo-error-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    document.getElementById('promo-error-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    });
}

function _showWipModal(title, text) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">${title}</p>
            <p class="svc-wip-text">${text}</p>
            <button class="svc-wip-btn" type="button" id="promo-wip-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    document.getElementById('promo-wip-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    });
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
}

// ── Кнопка оплаты ─────────────────────────────────────────────────────────
function initPayBtn() {
    const payBtn = document.getElementById('promo-pay-btn');
    if (!payBtn) return;

    payBtn.addEventListener('click', () => {
        if (!_agreed) {
            const block = document.getElementById('promo-agree-block');
            if (block) {
                block.classList.add('tc-agree-block--error');
                block.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                block.classList.add('tc-pay-btn--shake');
                setTimeout(() => block.classList.remove('tc-pay-btn--shake'), 400);
            }
            return;
        }
        if (_paymentMethod === 'stars') {
            initiateStarsPayment();
        } else {
            initiateCardPayment();
        }
    });
}

// ── Монтирование чекаута ──────────────────────────────────────────────────
export function mountPromotionCheckout(container, onBack, onSuccess) {
    _onPaymentSuccess = onSuccess || null;

    // Сброс состояния
    _agreed             = false;
    _paymentMethod      = 'stars';
    _selectedGiveawayId = null;
    _selectedTimeType   = 'immediate';
    _scheduledAt        = null;
    if (_checkoutTimerInterval) { clearInterval(_checkoutTimerInterval); _checkoutTimerInterval = null; }

    // Рендер
    container.innerHTML = promotionCheckoutTemplate();
    setShellVisibility(false);

    const handleBack = () => {
        if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
        setShellVisibility(true);
        hideBackButton(handleBack);
        if (typeof onBack === 'function') onBack();
    };
    showBackButton(handleBack);

    // Инициализация
    loadGiveaways();
    initTimeSelection();
    initPaymentSelection();
    initAgreeBlock();
    initLegalLinks();
    initPayBtn();
}
