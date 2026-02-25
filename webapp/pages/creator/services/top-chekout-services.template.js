// webapp/pages/creator/services/top-checkout-services.template.js

// ── Периоды размещения ────────────────────────────────────────────────────
const TOP_PERIODS = [
    { id: 'day',  label: '1 сутки',  price: 149 },
    { id: 'week', label: '1 неделя', price: 499 },
];

export default function topCheckoutTemplate() {
    return `
        <!-- Шапка с кнопкой назад -->
        <div class="tc-header">
            <button class="tc-back-btn" type="button" id="tc-back-btn">
                <svg width="9" height="16" viewBox="0 0 9 16" fill="none">
                    <path d="M8 1L1 8L8 15" stroke="currentColor" stroke-width="2"
                          stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Назад
            </button>
            <h2 class="tc-title">Включение в Топ</h2>
        </div>

        <!-- Выбор розыгрыша -->
        <div class="tc-section">
            <p class="tc-section-label">Выберите розыгрыш</p>
            <div class="tc-giveaway-list" id="tc-giveaway-list">
                <div class="tc-loading">Загрузка...</div>
            </div>
        </div>

        <!-- Выбор периода (скрыт до выбора розыгрыша) -->
        <div class="tc-section tc-section--hidden" id="tc-period-section">
            <p class="tc-section-label">Период размещения</p>
            <div class="tc-period-list">
                ${TOP_PERIODS.map(p => `
                    <div class="tc-period-card"
                         data-period-id="${p.id}"
                         data-price="${p.price}"
                         role="button"
                         tabindex="0">
                        <span class="tc-period-label">${p.label}</span>
                        <span class="tc-period-price">${p.price} ₽</span>
                    </div>
                `).join('')}
            </div>
        </div>

        <!-- Итог оплаты (скрыт до выбора периода) -->
        <div class="tc-section tc-section--hidden" id="tc-summary-section">
            <div class="tc-summary-card">
                <div class="tc-summary-row">
                    <span class="tc-summary-label">Продвижение в топ</span>
                    <span class="tc-summary-price" id="tc-summary-price">—</span>
                </div>
                <div class="tc-summary-divider"></div>
                <div class="tc-summary-row tc-summary-row--total">
                    <span class="tc-summary-label">Итого к оплате</span>
                    <span class="tc-summary-price" id="tc-summary-total">—</span>
                </div>
            </div>

            <!-- Согласие с офертой -->
            <p class="tc-legal-text">
                Нажимая «Перейти к оплате», я ознакомлен с
                <a class="tc-legal-link"
                   href="https://prizeme.ru/legal.html?doc=offer"
                   data-tg-link>офертой</a>
                и
                <a class="tc-legal-link"
                   href="https://prizeme.ru/legal.html?doc=terms"
                   data-tg-link>соглашением</a>
            </p>
        </div>

        <!-- Отступ под фиксированную кнопку -->
        <div class="svc-bottom-spacer"></div>

        <!-- Кнопка «Перейти к оплате» -->
        <div class="svc-footer tc-footer--hidden" id="tc-footer-pay">
            <button class="svc-continue-btn" id="tc-pay-btn" type="button">
                Перейти к оплате
            </button>
        </div>
    `;
}
