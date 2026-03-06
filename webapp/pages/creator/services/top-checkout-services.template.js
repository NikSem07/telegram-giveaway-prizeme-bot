// webapp/pages/creator/services/top-checkout-services.template.js

// Цены в Stars и рублях по методу оплаты
const TOP_PERIODS = [
    { id: 'day',  label: '1 День (24 часа)', priceRub: PRICES.day.rub,  priceStars: PRICES.day.stars  },
    { id: 'week', label: '1 Неделя',          priceRub: PRICES.week.rub, priceStars: PRICES.week.stars },
];

export default function topCheckoutTemplate(PRICES = { day: { rub: 149, stars: 149 }, week: { rub: 499, stars: 499 } }) {
    return `
        <!-- Шапка -->
        <div class="tc-header">
            <div class="tc-header-info">
                <h2 class="tc-title">🏆 Включение в топ-розыгрыши</h2>
                <p class="tc-subtitle">Розыгрыш будет опубликован в блоке «Топ-розыгрыши» на главной странице режима «Участник»</p>
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
                         data-price-rub="${p.priceRub}"
                         data-price-stars="${p.priceStars}"
                         role="button"
                         tabindex="0">
                        <span class="tc-period-label">${p.label}</span>
                        <span class="tc-period-price" data-price-rub="${p.priceRub}" data-price-stars="${p.priceStars}">${p.priceRub} ₽</span>
                    </div>
                `).join('')}
            </div>
        </div>

        <!-- Способ оплаты -->
        <div class="tc-section tc-section--hidden" id="tc-payment-section">
            <p class="tc-section-label">Способ оплаты</p>
            <div class="tc-payment-list">
                <div class="tc-payment-card tc-payment-card--active"
                     data-payment="card" role="button" tabindex="0">
                    <div class="tc-payment-icon">
                        <svg width="22" height="18" viewBox="0 0 22 18" fill="none">
                            <rect x="1" y="1" width="20" height="16" rx="3"
                                  stroke="currentColor" stroke-width="1.8"/>
                            <path d="M1 6h20" stroke="currentColor" stroke-width="1.8"/>
                            <rect x="4" y="10" width="4" height="2" rx="1" fill="currentColor"/>
                        </svg>
                    </div>
                    <span class="tc-payment-label">Картой</span>
                    <div class="tc-payment-check" id="tc-pay-check-card">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                            <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                                  stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </div>
                </div>

                <div class="tc-payment-card"
                     data-payment="stars" role="button" tabindex="0">
                    <div class="tc-payment-icon">
                        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                            <path d="M11 2L13.5 8.5L20.5 9L15.5 13.5L17.5 20.5L11 16.5L4.5 20.5L6.5 13.5L1.5 9L8.5 8.5L11 2Z"
                                  stroke="currentColor" stroke-width="1.8"
                                  stroke-linejoin="round"/>
                        </svg>
                    </div>
                    <span class="tc-payment-label">Stars</span>
                    <div class="tc-payment-check" id="tc-pay-check-stars">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
                        </svg>
                    </div>
                </div>
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
        
        <!-- Правовой дисклеймер (показывается после выбора периода) -->
        <div class="tc-disclaimer tc-section--hidden" id="tc-disclaimer">
            <p class="tc-disclaimer-text">
                Услуга «Включение в топ-розыгрыши» производится по единоразовой оплате.
                В зависимости от выбранного периода Ваш розыгрыш будет размещён в mini-app PrizeMe
                в разделе «Главная» режима «Участник». По истечению оплаченного периода услуга будет
                деактивирована, возобновить её можно при повторном оформлении. При оплате услуги вы
                подтверждаете, что ознакомились с
                <a class="tc-disclaimer-link" href="https://prizeme.ru/legal.html?doc=privacy" data-tg-link>политикой конфиденциальности</a>,
                где также указана контактная информация. В случае возникновения проблем или по вопросам
                возврата обращаться <a class="tc-disclaimer-link" href="https://t.me/prizeme_support" data-tg-support>@prizeme_support</a>.
            </p>
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
