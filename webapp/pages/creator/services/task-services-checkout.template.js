// webapp/pages/creator/services/task-services-checkout.template.js

export default function taskCheckoutTemplate({ taskCount, description, priceRub, priceStars }) {
    return `
        <div class="tc-screen">
        <!-- Шапка -->
        <div class="tc-header">
            <div class="tc-header-info">
                <h2 class="tc-title">Оплата размещения задания</h2>
                <p class="tc-subtitle">${description || 'Задания для участников розыгрыша'}</p>
            </div>
        </div>

        <!-- Сводка пулла -->
        <div class="tc-section">
            <p class="tc-section-label">Состав заказа</p>
            <div class="tc-summary-card tsc-order-card">
                <div class="tc-summary-row">
                    <span class="tc-summary-label">Количество заданий</span>
                    <span class="tc-summary-price">${taskCount}</span>
                </div>
                <div class="tc-summary-divider"></div>
                <div class="tc-summary-row">
                    <span class="tc-summary-label">Цена за задание</span>
                    <span class="tc-summary-price tsc-price-per-task" data-rub="${priceRub}" data-stars="${priceStars}">${priceRub} ₽</span>
                </div>
            </div>
        </div>

        <!-- Выбор розыгрыша -->
        <div class="tc-section">
            <p class="tc-section-label">Выберите розыгрыш</p>
            <div class="tc-giveaway-list" id="tsc-giveaway-list">
                <div class="tc-loading">Загрузка...</div>
            </div>
        </div>

        <!-- Способ оплаты (скрыт до выбора розыгрыша) -->
        <div class="tc-section tc-section--hidden" id="tsc-payment-section">
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
                    <div class="tc-payment-check">
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
                    <div class="tc-payment-check">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
                        </svg>
                    </div>
                </div>
            </div>
        </div>

        <!-- Итог к оплате (скрыт до выбора розыгрыша) -->
        <div class="tc-section tc-section--hidden" id="tsc-summary-section">
            <div class="tc-summary-card">
                <div class="tc-summary-row">
                    <span class="tc-summary-label">Задания (${taskCount} шт.)</span>
                    <span class="tc-summary-price" id="tsc-summary-price">—</span>
                </div>
                <div class="tc-summary-divider"></div>
                <div class="tc-summary-row tc-summary-row--total">
                    <span class="tc-summary-label">Итого к оплате</span>
                    <span class="tc-summary-price" id="tsc-summary-total">—</span>
                </div>
            </div>

            <!-- Согласие с офертой -->
            <div class="tc-agree-block" id="tsc-agree-block" role="button" tabindex="0">
                <div class="tc-agree-checkbox" id="tsc-agree-checkbox">
                    <svg class="tc-agree-check" id="tsc-agree-check" width="12" height="10"
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

        <!-- Дисклеймер (скрыт до выбора розыгрыша) -->
        <div class="tc-disclaimer tc-section--hidden" id="tsc-disclaimer">
            <p class="tc-disclaimer-text">
                Услуга «Задания для участников» оплачивается единоразово за каждый пулл заданий.
                После оплаты задания будут привязаны к выбранному розыгрышу и станут доступны
                всем его участникам в разделе «Задания». Стоимость составляет ${priceRub} ₽ за каждое
                задание в пулле. При оплате вы подтверждаете, что ознакомились с
                <a class="tc-disclaimer-link" href="https://prizeme.ru/legal.html?doc=privacy" data-tg-link>политикой конфиденциальности</a>.
                По вопросам возврата и поддержки обращайтесь:
                <a class="tc-disclaimer-link" href="https://t.me/prizeme_support" data-tg-support>@prizeme_support</a>.
            </p>
        </div>

        <div class="svc-bottom-spacer"></div>

        <!-- Кнопка оплаты -->
        <div class="svc-footer tc-footer--hidden" id="tsc-footer-pay">
            <button class="svc-continue-btn tc-pay-btn--inactive" id="tsc-pay-btn" type="button">
                Перейти к оплате
            </button>
        </div>
        </div>
    `;
}
