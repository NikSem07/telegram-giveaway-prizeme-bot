// webapp/pages/creator/services/promotion-services.js
import promotionCheckoutTemplate from './promotion-services.template.js';

// ── Цены (меняй здесь в одном месте) ─────────────────────────────────────
const PROMOTION_PRICE_RUB   = 9990;   // ₽
const PROMOTION_PRICE_STARS = 9990;   // ⭐

// ── Состояние ─────────────────────────────────────────────────────────────
let _agreed             = false;
let _paymentMethod      = 'card';      // card | stars — по умолчанию "Картой"
let _selectedGiveawayId = null;
let _selectedGiveawayEndAt = null;     // ISO — для валидации даты
let _selectedTimeType   = 'immediate'; // immediate | scheduled
let _scheduledAt        = null;
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
                     data-giveaway-id="${g.id}"
                     data-giveaway-end="${g.end_at_utc || ''}"
                     role="button" tabindex="0">
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
    _selectedGiveawayId    = card.dataset.giveawayId || null;
    _selectedGiveawayEndAt = card.dataset.giveawayEnd || null;

    const ch = card.querySelector('.tc-giveaway-check');
    if (ch) ch.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#007AFF"/>
            <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;

    // Сбрасываем время и показываем все блоки сразу (правка №3)
    _selectedTimeType = 'immediate';
    _scheduledAt      = null;

    // Сбрасываем пикер
    const picker = document.getElementById('promo-datetime-input');
    if (picker) picker.value = '';
    const hint = document.getElementById('promo-datetime-hint');
    if (hint) hint.textContent = '';
    document.getElementById('promo-datetime-picker')?.classList.add('tc-section--hidden');

    // Сбрасываем выбор времени на "Сразу"
    document.querySelectorAll('.promo-time-card').forEach(c => {
        const isImmediate = c.dataset.timeType === 'immediate';
        c.classList.toggle('promo-time-card--active', isImmediate);
        const checkId = `promo-time-check-${c.dataset.timeType}`;
        const checkEl = document.getElementById(checkId);
        if (!checkEl) return;
        checkEl.innerHTML = isImmediate
            ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="#007AFF"/><path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/></svg>`;
    });

    // Показываем ВСЕ блоки сразу (правка №3)
    const timeSection = document.getElementById('promo-time-section');
    timeSection?.classList.remove('tc-section--hidden');
    _showPaymentBlocks();

    timeSection?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Выбор времени публикации ──────────────────────────────────────────────
function initTimeSelection() {
    document.querySelectorAll('.promo-time-card').forEach(card => {
        card.addEventListener('click', () => onTimeSelected(card));
    });

    const picker = document.getElementById('promo-datetime-input');
    if (!picker) return;

    picker.addEventListener('change', () => {
        if (!picker.value) return;

        const hint = document.getElementById('promo-datetime-hint');
        const selectedMs = new Date(picker.value).getTime();
        const nowMs      = Date.now();
        const minMs      = nowMs + 24 * 60 * 60 * 1000; // минимум +24 часа (правка №5)

        // Валидация: не раньше чем через 24 часа
        if (selectedMs < minMs) {
            if (hint) {
                hint.textContent = '⚠️ Выберите время минимум через 24 часа от текущего момента';
                hint.style.color = 'var(--color-danger, #FF3B30)';
            }
            _scheduledAt = null;
            return;
        }

        // Валидация: не позже окончания розыгрыша (правка №5)
        if (_selectedGiveawayEndAt) {
            const endMs = new Date(_selectedGiveawayEndAt).getTime();
            if (selectedMs >= endMs) {
                if (hint) {
                    const endStr = new Date(_selectedGiveawayEndAt).toLocaleString('ru-RU', {
                        day: '2-digit', month: '2-digit', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                    });
                    hint.textContent = `⚠️ Дата публикации должна быть раньше окончания розыгрыша (${endStr})`;
                    hint.style.color = 'var(--color-danger, #FF3B30)';
                }
                _scheduledAt = null;
                return;
            }
        }

        // Всё ок
        _scheduledAt = new Date(picker.value).toISOString();
        if (hint) {
            const d = new Date(picker.value);
            hint.textContent = '✓ ' + d.toLocaleString('ru-RU', {
                day: '2-digit', month: '2-digit', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            }) + ' (МСК)';
            hint.style.color = 'var(--color-primary, #007AFF)';
        }

        const descEl = document.getElementById('promo-scheduled-desc');
        if (descEl) {
            const d = new Date(picker.value);
            descEl.textContent = d.toLocaleString('ru-RU', {
                day: '2-digit', month: '2-digit', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            }) + ' (МСК)';
        }
    });
}

function onTimeSelected(card) {
    const timeType = card.dataset.timeType;
    _selectedTimeType = timeType;

    document.querySelectorAll('.promo-time-card').forEach(c => {
        const isActive = c.dataset.timeType === timeType;
        c.classList.toggle('promo-time-card--active', isActive);
        const checkId = `promo-time-check-${c.dataset.timeType}`;
        const checkEl = document.getElementById(checkId);
        if (!checkEl) return;
        checkEl.innerHTML = isActive
            ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="#007AFF"/><path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/></svg>`;
    });

    const pickerWrap = document.getElementById('promo-datetime-picker');
    const picker     = document.getElementById('promo-datetime-input');

    if (timeType === 'immediate') {
        _scheduledAt = null;
        pickerWrap?.classList.add('tc-section--hidden');
        if (picker) picker.value = '';
        const hint = document.getElementById('promo-datetime-hint');
        if (hint) hint.textContent = '';
    } else {
        // Показываем пикер (правка №4 — широкий блок)
        pickerWrap?.classList.remove('tc-section--hidden');
        pickerWrap?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Устанавливаем min: сейчас + 24 часа (правка №5)
        if (picker) {
            const minDate = new Date(Date.now() + 24 * 60 * 60 * 1000);
            picker.min = minDate.toISOString().slice(0, 16);

            // Устанавливаем max: окончание розыгрыша (правка №5)
            if (_selectedGiveawayEndAt) {
                const maxDate = new Date(new Date(_selectedGiveawayEndAt).getTime() - 60 * 1000);
                picker.max = maxDate.toISOString().slice(0, 16);
            }

            // Автофокус чтобы пользователь понял что надо нажать
            setTimeout(() => { try { picker.focus(); picker.click(); } catch (e) {} }, 100);
        }
    }
}

// ── Показ / сброс блоков оплаты ───────────────────────────────────────────
function _showPaymentBlocks() {
    ['promo-payment-section', 'promo-summary-section', 'promo-disclaimer'].forEach(id => {
        document.getElementById(id)?.classList.remove('tc-section--hidden');
    });
    const footer = document.getElementById('promo-footer-pay');
    if (footer) {
        footer.classList.remove('tc-footer--hidden');
        footer.classList.add('is-visible');
    }
    _updateSummaryDisplay();
}

// ── Итог ──────────────────────────────────────────────────────────────────
function _updateSummaryDisplay() {
    const isStars = _paymentMethod === 'stars';
    const text    = isStars
        ? `${PROMOTION_PRICE_STARS.toLocaleString('ru-RU')} ⭐`
        : `${PROMOTION_PRICE_RUB.toLocaleString('ru-RU')} ₽`;
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
                    ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="#007AFF"/><path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
                    : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/></svg>`;
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
    _showInfoModal('🚧 В разработке', 'Оплата картой скоро будет доступна. Используйте Telegram Stars.');
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
    _showInfoModal('❌ Ошибка оплаты', reason || 'Не удалось провести оплату. Попробуйте ещё раз.');
}

function _showInfoModal(title, text) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">${title}</p>
            <p class="svc-wip-text">${text}</p>
            <button class="svc-wip-btn" type="button" id="promo-info-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    const close = () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    };
    document.getElementById('promo-info-close').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
}

// ── Кнопка оплаты ─────────────────────────────────────────────────────────
function initPayBtn() {
    const payBtn = document.getElementById('promo-pay-btn');
    if (!payBtn) return;

    payBtn.addEventListener('click', () => {
        if (!_agreed) {
            const agreeBlock = document.getElementById('promo-agree-block');
            agreeBlock?.classList.remove('tc-agree-block--error');
            payBtn.classList.remove('tc-pay-btn--shake');
            void payBtn.offsetWidth; // reflow для перезапуска анимации
            agreeBlock?.classList.add('tc-agree-block--error');
            payBtn.classList.add('tc-pay-btn--shake');
            if (navigator.vibrate) navigator.vibrate(80);
            payBtn.addEventListener('animationend', () => {
                payBtn.classList.remove('tc-pay-btn--shake');
            }, { once: true });
            agreeBlock?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }

        // Для scheduled — проверяем что дата выбрана и валидна
        if (_selectedTimeType === 'scheduled' && !_scheduledAt) {
            const picker = document.getElementById('promo-datetime-input');
            picker?.focus();
            const hint = document.getElementById('promo-datetime-hint');
            if (hint && !hint.textContent) {
                hint.textContent = '⚠️ Укажите дату и время публикации';
                hint.style.color = 'var(--color-danger, #FF3B30)';
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

// ── Монтирование ──────────────────────────────────────────────────────────
export function mountPromotionCheckout(container, onBack, onSuccess) {
    _onPaymentSuccess      = onSuccess || null;
    _agreed                = false;
    _paymentMethod         = 'card';
    _selectedGiveawayId    = null;
    _selectedGiveawayEndAt = null;
    _selectedTimeType      = 'immediate';
    _scheduledAt           = null;
    if (_checkoutTimerInterval) { clearInterval(_checkoutTimerInterval); _checkoutTimerInterval = null; }

    container.innerHTML = promotionCheckoutTemplate();
    setShellVisibility(false);

    const handleBack = () => {
        if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);
        setShellVisibility(true);
        hideBackButton(handleBack);
        if (typeof onBack === 'function') onBack();
    };
    showBackButton(handleBack);

    loadGiveaways();
    initTimeSelection();
    initPaymentSelection();
    initAgreeBlock();
    initLegalLinks();
    initPayBtn();
}
