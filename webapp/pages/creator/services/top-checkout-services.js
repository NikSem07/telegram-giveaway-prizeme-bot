// webapp/pages/creator/services/top-checkout-services.js
import topCheckoutTemplate from './top-checkout-services.template.js';

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
    const bottomNav = document.querySelector('.bottom-nav');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';
    if (bottomNav) bottomNav.style.display = visible ? '' : 'none';
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

        listEl.querySelectorAll('.tc-giveaway-card').forEach(card => {
            card.addEventListener('click', () => onGiveawaySelected(card));
        });

        // Запускаем таймеры
        startCheckoutTimers();

    } catch (e) {
        listEl.innerHTML = `<div class="tc-empty"><p class="tc-empty-text">Ошибка загрузки. Попробуйте ещё раз.</p></div>`;
        console.error('[TOP_CHECKOUT] loadGiveaways error:', e);
    }
}

// ── Таймеры обратного отсчёта ─────────────────────────────────────────────
let _checkoutTimerInterval = null;

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
    document.getElementById('tc-footer-pay').classList.add('tc-footer--hidden');
    _paymentMethod = 'card';
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

// ── Выбор периода ─────────────────────────────────────────────────────────
function onPeriodSelected(card) {
    document.querySelectorAll('.tc-period-card').forEach(c => c.classList.remove('tc-period-card--active'));
    card.classList.add('tc-period-card--active');

    const price     = Number(card.dataset.price);
    const priceText = `${price} ₽`;

    document.getElementById('tc-summary-price').textContent = priceText;
    document.getElementById('tc-summary-total').textContent = priceText;

    document.getElementById('tc-payment-section').classList.remove('tc-section--hidden');
    document.getElementById('tc-summary-section').classList.remove('tc-section--hidden');

    const footerPay = document.getElementById('tc-footer-pay');
    footerPay.classList.remove('tc-footer--hidden');
    footerPay.classList.add('is-visible');
}

// ── Согласие с офертой ────────────────────────────────────────────────────
let _agreed = false;
let _paymentMethod = 'card'; // card | wallet

function initPaymentSelection() {
    document.querySelectorAll('.tc-payment-card').forEach(card => {
        card.addEventListener('click', () => {
            const method = card.dataset.payment;
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
}

// ── Заглушка оплаты ───────────────────────────────────────────────────────
function showWipModal() {
    const modal = document.createElement('div');
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🚧 В разработке</p>
            <p class="svc-wip-text">Оплата скоро будет доступна. Следите за обновлениями!</p>
            <button class="svc-wip-btn" type="button" id="svc-wip-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('is-visible'));

    const close = () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    };
    document.getElementById('svc-wip-close').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
}

// ── Публичный API ─────────────────────────────────────────────────────────
function mountTopCheckout(container, onBack) {
    _agreed = false;

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
            // Тряска кнопки + красная обводка блока согласия
            const payBtn    = document.getElementById('tc-pay-btn');
            const agreeBlock = document.getElementById('tc-agree-block');

            agreeBlock.classList.remove('tc-agree-block--error');
            payBtn.classList.remove('tc-pay-btn--shake');
            void payBtn.offsetWidth; // reflow
            agreeBlock.classList.add('tc-agree-block--error');
            payBtn.classList.add('tc-pay-btn--shake');

            if (navigator.vibrate) navigator.vibrate(80);

            payBtn.addEventListener('animationend', () => {
                payBtn.classList.remove('tc-pay-btn--shake');
            }, { once: true });

            return;
        }
        showWipModal();
    });

    initPaymentSelection();
    initAgreeBlock();
    initLegalLinks();
    loadGiveaways();
}

export { mountTopCheckout };
