// webapp/pages/creator/services/top-checkout-services.template.js

const TOP_PERIODS = [
    { id: 'day',  label: '1 День (24 часа)', price: 149 },
    { id: 'week', label: '1 Неделя',          price: 499 },
];

export default function topCheckoutTemplate() {
    return `
        <!-- Шапка -->
        <div class="tc-header">
            <div class="tc-header-info">
                <h2 class="tc-title">🏆 Включение в топ-розыгрыши</h2>
                <p class="tc-subtitle">Ваш розыгрыш будет показан в блоке «Топ» на главной странице. Каждый участник увидит его сразу при открытии приложения.</p>
            </div>
        </div>

        <!-- Выбор розыгрыша -->
        <div class="tc-section">
            <p class="tc-section-label">Выберите розыгрыш</p>
            <div class="tc-giveaway-list" id="tc-giveaway-list">
                <div class="tc-loading">Загрузка...</div>
            </div>
        </div>

        <!-- Выбор периода -->
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

        <!-- Итог оплаты -->
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
            <div class="tc-agree-block" id="tc-agree-block" role="button" tabindex="0">
                <div class="tc-agree-checkbox" id="tc-agree-checkbox">
                    <svg class="tc-agree-check" id="tc-agree-check" width="12" height="10"
                         viewBox="0 0 12 10" fill="none" style="display:none;">
                        <path d="M1 5L4.5 8.5L11 1" stroke="white" stroke-width="2"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <p class="tc-agree-text">
                    Я ознакомлен с
                    <a class="tc-legal-link" href="https://prizeme.ru/legal.html?doc=offer" data-tg-link>офертой</a>
                    и
                    <a class="tc-legal-link" href="https://prizeme.ru/legal.html?doc=terms" data-tg-link>соглашением</a>
                </p>
            </div>
        </div>

        <div class="svc-bottom-spacer"></div>

        <!-- Кнопка «Перейти к оплате» -->
        <div class="svc-footer tc-footer--hidden" id="tc-footer-pay">
            <button class="svc-continue-btn tc-pay-btn--inactive" id="tc-pay-btn" type="button">
                Перейти к оплате
            </button>
        </div>
    `;
}
