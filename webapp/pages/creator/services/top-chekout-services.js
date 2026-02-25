// webapp/pages/creator/services/top-checkout-services.js
import topCheckoutTemplate from './top-checkout-services.template.js';

// ── Скрыть/показать шапку и навбар ───────────────────────────────────────
function setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    const bottomNav = document.querySelector('.bottom-nav');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';
    if (bottomNav) bottomNav.style.display = visible ? '' : 'none';
}

// ── Загрузка розыгрышей создателя ────────────────────────────────────────
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
            listEl.innerHTML = `
                <div class="tc-empty">
                    <p class="tc-empty-text">Нет активных розыгрышей для продвижения</p>
                </div>`;
            return;
        }

        listEl.innerHTML = data.items.map(g => `
            <div class="tc-giveaway-card"
                 data-giveaway-id="${g.id}"
                 role="button"
                 tabindex="0">
                <span class="tc-giveaway-title">${g.title}</span>
                <span class="tc-giveaway-channels">${(g.channels || []).join(', ') || '—'}</span>
            </div>
        `).join('');

        listEl.querySelectorAll('.tc-giveaway-card').forEach(card => {
            card.addEventListener('click', () => onGiveawaySelected(card));
        });

    } catch (e) {
        listEl.innerHTML = `
            <div class="tc-empty">
                <p class="tc-empty-text">Ошибка загрузки. Попробуйте ещё раз.</p>
            </div>`;
        console.error('[TOP_CHECKOUT] loadGiveaways error:', e);
    }
}

// ── Выбор розыгрыша ───────────────────────────────────────────────────────
function onGiveawaySelected(card) {
    // Снимаем выделение с остальных
    document.querySelectorAll('.tc-giveaway-card').forEach(c => {
        c.classList.remove('tc-giveaway-card--active');
    });

    card.classList.add('tc-giveaway-card--active');

    // Показываем секцию выбора периода
    const periodSection = document.getElementById('tc-period-section');
    periodSection.classList.remove('tc-section--hidden');
    periodSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Сбрасываем выбор периода и скрываем итог
    document.querySelectorAll('.tc-period-card').forEach(p => {
        p.classList.remove('tc-period-card--active');
    });
    document.getElementById('tc-summary-section').classList.add('tc-section--hidden');
    document.getElementById('tc-footer-pay').classList.add('tc-footer--hidden');
    document.getElementById('tc-footer-pay').setAttribute('aria-hidden', 'true');
}

// ── Выбор периода ─────────────────────────────────────────────────────────
function onPeriodSelected(card) {
    document.querySelectorAll('.tc-period-card').forEach(c => {
        c.classList.remove('tc-period-card--active');
    });
    card.classList.add('tc-period-card--active');

    const price     = Number(card.dataset.price);
    const priceText = `${price} ₽`;

    document.getElementById('tc-summary-price').textContent = priceText;
    document.getElementById('tc-summary-total').textContent = priceText;

    // Показываем итог и кнопку оплаты
    document.getElementById('tc-summary-section').classList.remove('tc-section--hidden');

    const footerPay = document.getElementById('tc-footer-pay');
    footerPay.classList.remove('tc-footer--hidden');
    footerPay.setAttribute('aria-hidden', 'false');
    footerPay.classList.add('is-visible');
}

// ── Открытие ссылки во встроенном браузере Telegram ───────────────────────
function openTgLink(url) {
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) {
        tg.openLink(url, { try_instant_view: true });
    } else {
        window.open(url, '_blank');
    }
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

// ── Публичный API: инициализация и разрушение ─────────────────────────────

/**
 * Монтирует экран чекаута в переданный контейнер.
 * @param {HTMLElement} container — элемент куда рендерим
 * @param {Function}    onBack    — callback при нажатии «Назад»
 */
function mountTopCheckout(container, onBack) {
    container.innerHTML = topCheckoutTemplate();
    setShellVisibility(false);

    // Назад
    document.getElementById('tc-back-btn').addEventListener('click', () => {
        setShellVisibility(true);
        onBack();
    });

    // Периоды
    document.querySelectorAll('.tc-period-card').forEach(card => {
        card.addEventListener('click', () => onPeriodSelected(card));
    });

    // Кнопка оплаты
    document.getElementById('tc-pay-btn').addEventListener('click', showWipModal);

    // Ссылки оферты
    document.querySelectorAll('[data-tg-link]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            openTgLink(link.href);
        });
    });

    // Загружаем розыгрыши
    loadGiveaways();
}

export { mountTopCheckout };
