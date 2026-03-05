// webapp/pages/creator/services/top-checkout-services.js
import topCheckoutTemplate from './top-checkout-services.template.js';

// ── Состояние чекаута ─────────────────────────────────────────────────────
let _agreed             = false;
let _paymentMethod      = 'card';   // card | stars
let _selectedGiveawayId = null;
let _selectedPeriodId   = null;
let _selectedPriceRub   = null;
let _selectedPriceStars = null;
let _checkoutTimerInterval = null;

// ── Системная кнопка Back Telegram ───────────────────────────────────────
function showBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try {
        tg.BackButton.show();
        tg.BackButton.onClick(onBack);
    } catch (e) {}
}

function hideBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try {
        tg.BackButton.offClick(onBack);
        tg.BackButton.hide();
    } catch (e) {}
}

// ── Шапка и навбар ───────────────────────────────────────────────────────
function setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';

    // Используем класс на body — как для карточек розыгрышей.
    // Это скрывает навбар через CSS-трансформ И обнуляет --navbar-height,
    // чтобы фиксированные кнопки корректно прижимались к низу.
    if (visible) {
        document.body.classList.remove('page-checkout-services');
    } else {
        document.body.classList.add('page-checkout-services');
    }
}

// ── Загрузка розыгрышей ───────────────────────────────────────────────────
async function loadGiveaways() {
    const listEl = document.getElementById('tc-giveaway-list');
    if (!listEl) return;

    try {
        const initData = window.Telegram?.WebApp?.initData || '';
        const resp = await fetch('/api/top_placement_checkout_data', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ init_data: initData }),
        });
        const data = await resp.json();

        if (!data.ok || !data.items.length) {
            listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Нет активных розыгрышей для продвижения</p></div>`;
            return;
        }

        // Рендерим карточки в стиле каталога с главной страницы
        listEl.innerHTML = data.items.map(g => {
            const channels = (g.channels || []).join(', ') || '—';
            const avatarUrl = g.first_channel_avatar_url || null;
            const timerId = `tc-timer-${g.id}`;
            const endDate = g.end_at_utc || null;

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
                    <div class="tc-giveaway-check" id="tc-check-${g.id}">
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
            onGiveawaySelected(card);
        });

        // Запускаем таймеры
        startCheckoutTimers();

    } catch (e) {
        listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Ошибка загрузки. Попробуйте ещё раз.</p></div>`;
        console.error('[TOP_CHECKOUT] loadGiveaways error:', e);
    }
}

// ── Таймеры обратного отсчёта ─────────────────────────────────────────────
function formatCountdown(endUtc) {
    const now  = Date.now();
    const end  = new Date(endUtc).getTime();
    let   diff = Math.max(0, Math.floor((end - now) / 1000));

    const days = Math.floor(diff / 86400);
    diff -= days * 86400;
    const hours = Math.floor(diff / 3600);
    diff -= hours * 3600;
    const mins = Math.floor(diff / 60);
    const secs = diff - mins * 60;

    const pad = n => String(n).padStart(2, '0');
    return days > 0
        ? `${days} дн., ${pad(hours)}:${pad(mins)}:${pad(secs)}`
        : `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
}

function startCheckoutTimers() {
    if (_checkoutTimerInterval) clearInterval(_checkoutTimerInterval);

    const tick = () => {
        document.querySelectorAll('.giveaway-timer[data-end]').forEach(el => {
            const end = el.dataset.end;
            if (!end) return;
            el.textContent = formatCountdown(end);
        });
    };

    tick();
    _checkoutTimerInterval = setInterval(tick, 1000);
}

// ── Выбор розыгрыша ───────────────────────────────────────────────────────
function onGiveawaySelected(card) {
    document.querySelectorAll('.tc-giveaway-card').forEach(c => {
        c.classList.remove('tc-giveaway-card--active');
        // Сбрасываем иконку галочки
        const checkEl = c.querySelector('.tc-giveaway-check');
        if (checkEl) checkEl.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
            </svg>`;
    });

    card.classList.add('tc-giveaway-card--active');
    _selectedGiveawayId = card.dataset.giveawayId || null;
    console.log('[CHECKOUT] giveaway selected, id =', _selectedGiveawayId);

    // Показываем галочку выбора
    const checkEl = card.querySelector('.tc-giveaway-check');
    if (checkEl) checkEl.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#007AFF"/>
            <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;

    // Показываем выбор периода
    const periodSection = document.getElementById('tc-period-section');
    periodSection.classList.remove('tc-section--hidden');
    periodSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Сбрасываем период и итог
    document.querySelectorAll('.tc-period-card').forEach(p => p.classList.remove('tc-period-card--active'));
    document.getElementById('tc-payment-section').classList.add('tc-section--hidden');
    document.getElementById('tc-summary-section').classList.add('tc-section--hidden');
    document.getElementById('tc-disclaimer').classList.add('tc-section--hidden');
    document.getElementById('tc-footer-pay').classList.add('tc-footer--hidden');
    _paymentMethod      = 'card';
    _selectedPeriodId   = null;
    _selectedPriceRub   = null;
    _selectedPriceStars = null;
    // _selectedGiveawayId НЕ сбрасываем — он уже установлен выше
    // Сбрасываем визуал карточек оплаты
    document.querySelectorAll('.tc-payment-card').forEach(c => {
        const isCard = c.dataset.payment === 'card';
        c.classList.toggle('tc-payment-card--active', isCard);
        const checkEl = c.querySelector('.tc-payment-check');
        if (!checkEl) return;
        checkEl.innerHTML = isCard
            ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                   <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                   <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                         stroke-linecap="round" stroke-linejoin="round"/>
               </svg>`
            : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                   <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
               </svg>`;
    });
}

// ── Обновление итога в зависимости от метода оплаты ──────────────────────
function _updateSummaryDisplay() {
    if (!_selectedPriceRub) return;

    const isStars   = _paymentMethod === 'stars';
    const priceText = isStars
        ? `${_selectedPriceStars} ⭐`
        : `${_selectedPriceRub} ₽`;

    document.getElementById('tc-summary-price').textContent = priceText;
    document.getElementById('tc-summary-total').textContent = priceText;
}

// ── Выбор периода ─────────────────────────────────────────────────────────
function onPeriodSelected(card) {
    document.querySelectorAll('.tc-period-card').forEach(c => c.classList.remove('tc-period-card--active'));
    card.classList.add('tc-period-card--active');

    _selectedPeriodId   = card.dataset.periodId;
    _selectedPriceRub   = Number(card.dataset.priceRub);
    _selectedPriceStars = Number(card.dataset.priceStars);

    // Обновляем отображение итога в зависимости от метода оплаты
    _updateSummaryDisplay();

    document.getElementById('tc-payment-section').classList.remove('tc-section--hidden');
    document.getElementById('tc-summary-section').classList.remove('tc-section--hidden');
    document.getElementById('tc-disclaimer').classList.remove('tc-section--hidden');

    const footerPay = document.getElementById('tc-footer-pay');
    footerPay.classList.remove('tc-footer--hidden');
    footerPay.classList.add('is-visible');
}

// ── Согласие с офертой ────────────────────────────────────────────────────
function initPaymentSelection() {
    document.querySelectorAll('.tc-payment-card').forEach(card => {
        card.addEventListener('click', () => {
            const method   = card.dataset.payment;
            _paymentMethod = method;

            // Обновляем активный стиль карточек
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

            // Обновляем цены на карточках периодов
            const isStars = method === 'stars';
            document.querySelectorAll('.tc-period-card').forEach(p => {
                const priceEl = p.querySelector('.tc-period-price');
                if (!priceEl) return;
                const rub   = priceEl.dataset.priceRub;
                const stars = priceEl.dataset.priceStars;
                priceEl.textContent = isStars ? `${stars} ⭐` : `${rub} ₽`;
            });

            // Пересчитываем итог если период уже выбран
            _updateSummaryDisplay();
        });
    });
}

function initAgreeBlock() {
    const block    = document.getElementById('tc-agree-block');
    const checkbox = document.getElementById('tc-agree-checkbox');
    const checkSvg = document.getElementById('tc-agree-check');
    const payBtn   = document.getElementById('tc-pay-btn');

    if (!block) return;

    block.addEventListener('click', (e) => {
        // Если клик по ссылке — не переключаем чекбокс
        if (e.target.closest('[data-tg-link]')) return;

        _agreed = !_agreed;

        // Чекбокс
        checkbox.classList.toggle('tc-agree-checkbox--checked', _agreed);
        checkSvg.style.display = _agreed ? 'block' : 'none';

        // Кнопка
        payBtn.classList.toggle('tc-pay-btn--inactive', !_agreed);

        // Убираем красную обводку если согласился
        if (_agreed) block.classList.remove('tc-agree-block--error');
    });
}

// ── Ссылки оферты ─────────────────────────────────────────────────────────
function initLegalLinks() {
    // Ссылки на документы — открываем в instant view, mini-app не закрывается
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

    // Ссылки на Telegram-аккаунты/боты — openTelegramLink, mini-app уходит в фон
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

// ── Оплата Stars — нативно через Telegram ────────────────────────────────
async function initiateStarsPayment() {
    const payBtn = document.getElementById('tc-pay-btn');
    payBtn.disabled = true;
    payBtn.textContent = 'Создаём счёт...';

    try {
        const initData = window.Telegram?.WebApp?.initData || '';
        const resp = await fetch('/api/create_stars_invoice', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   initData,
                giveaway_id: _selectedGiveawayId,
                period:      _selectedPeriodId,   // 'day' | 'week'
                stars:       _selectedPriceStars,
            }),
        });

        const data = await resp.json();

        if (!data.ok || !data.invoice_link) {
            throw new Error(data.reason || 'Не удалось создать счёт');
        }

        // Открываем нативный экран оплаты Telegram — mini-app остаётся открытым
        window.Telegram.WebApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                showPaymentSuccessModal();
            } else if (status === 'cancelled') {
                // Пользователь закрыл — просто возвращаем кнопку
                payBtn.disabled = false;
                payBtn.textContent = 'Перейти к оплате';
            } else if (status === 'failed') {
                showPaymentErrorModal();
            }
        });

    } catch (e) {
        console.error('[TOP_CHECKOUT] initiateStarsPayment error:', e);
        showPaymentErrorModal(e.message);
    } finally {
        payBtn.disabled = false;
        payBtn.textContent = 'Перейти к оплате';
    }
}

// ── Оплата картой (Robokassa) ────────────────
function loadRobokassaScript() {
    return new Promise((resolve, reject) => {
        if (window.Robokassa) { resolve(); return; }
        const s = document.createElement('script');
        s.src = 'https://auth.robokassa.ru/Merchant/bundle/robokassa_iframe.js';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

async function pollRobokassaStatus(invId, initData, maxAttempts = 300) {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        const timer = setInterval(async () => {
            attempts++;
            try {
                const r = await fetch(
                    `/api/robokassa_order_status?inv_id=${invId}&init_data=${encodeURIComponent(initData)}`
                );
                const d = await r.json();
                if (d.status === 'paid') {
                    clearInterval(timer);
                    resolve();
                } else if (d.status === 'failed') {
                    clearInterval(timer);
                    reject(new Error('Платёж отклонён'));
                } else if (attempts >= maxAttempts) {
                    clearInterval(timer);
                    reject(new Error('Время ожидания истекло'));
                }
            } catch (e) {
                if (attempts >= maxAttempts) {
                    clearInterval(timer);
                    reject(e);
                }
            }
        }, 2000);
    });
}

async function initiateCardPayment() {
    const payBtn = document.getElementById('tc-pay-btn');
    payBtn.disabled = true;
    payBtn.textContent = 'Загрузка...';

    try {
        await loadRobokassaScript();

        const initData = window.Telegram?.WebApp?.initData || '';
        const resp = await fetch('/api/create_robokassa_invoice', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                init_data:   initData,
                giveaway_id: _selectedGiveawayId,
                period:      _selectedPeriodId,
                price_rub:   _selectedPriceRub
            })
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason || 'Не удалось создать счёт');

        // Открываем Robokassa modal
        Robokassa.Render({
            MerchantLogin:  data.merchant_login,
            OutSum:         data.out_sum,
            InvId:          data.inv_id,
            Description:    data.description,
            Culture:        'ru',
            Encoding:       'utf-8',
            IsTest:         data.is_test,
            SignatureValue: data.signature,
            Settings:       JSON.stringify({ PaymentMethods: ['BankCard', 'SBP'], Mode: 'modal' })
        });

        payBtn.textContent = 'Ожидаем оплату...';

        // Polling статуса
        await pollRobokassaStatus(data.inv_id, initData);
        showPaymentSuccessModal();

    } catch (e) {
        console.error('[TOP_CHECKOUT] initiateCardPayment error:', e);
        showPaymentErrorModal(e.message);
    } finally {
        payBtn.disabled = false;
        payBtn.textContent = 'Перейти к оплате';
    }
}

// ── Переход на главную участника после успешной оплаты ───────────────────
let _onPaymentSuccess = null;

function showPaymentSuccessModal() {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🎉 Оплата прошла!</p>
            <p class="svc-wip-text">Ваш розыгрыш добавлен в топ. Размещение активировано.</p>
            <button class="svc-wip-btn" type="button" id="tc-success-close">Отлично!</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));

    document.getElementById('tc-success-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => {
            modal.remove();
            setShellVisibility(true);
            if (typeof _onPaymentSuccess === 'function') {
                _onPaymentSuccess();
            }
        }, { once: true });
    });
}

// ── Экран ошибки оплаты ───────────────────────────────────────────────────
function showPaymentErrorModal(reason) {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">❌ Ошибка оплаты</p>
            <p class="svc-wip-text">${reason || 'Не удалось провести оплату. Попробуйте ещё раз.'}</p>
            <button class="svc-wip-btn" type="button" id="tc-error-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    document.getElementById('tc-error-close').addEventListener('click', () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    });
}

// ── Публичный API ─────────────────────────────────────────────────────────
function mountTopCheckout(container, onBack, onPaymentSuccess) {
    _agreed = false;
    _onPaymentSuccess = onPaymentSuccess || null;

    container.innerHTML = topCheckoutTemplate();
    setShellVisibility(false);

    // Системная кнопка Back Telegram
    const handleBack = () => {
        hideBackButton(handleBack);
        setShellVisibility(true);
        onBack();
    };
    showBackButton(handleBack);

    // Периоды
    document.querySelectorAll('.tc-period-card').forEach(card => {
        card.addEventListener('click', () => onPeriodSelected(card));
    });

    // Кнопка оплаты
    document.getElementById('tc-pay-btn').addEventListener('click', () => {
        if (!_agreed) {
            const payBtn     = document.getElementById('tc-pay-btn');
            const agreeBlock = document.getElementById('tc-agree-block');

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

        if (_paymentMethod === 'stars') {
            initiateStarsPayment();
        } else {
            initiateCardPayment();
        }
    });

    initPaymentSelection();
    initAgreeBlock();
    initLegalLinks();
    loadGiveaways();
}

export { mountTopCheckout };
