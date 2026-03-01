// webapp/pages/creator/services/promotion-services.template.js

export default function promotionCheckoutTemplate() {
  return `
    <div class="tc-screen" id="promo-checkout-screen">

      <!-- Заголовок -->
      <div class="tc-header">
        <h2 class="tc-title">📣 Продвижение в боте</h2>
        <p class="tc-subtitle">Розыгрыш будет опубликован в боте - все пользователи получат уведомление с возможностью принять участие</p>
      </div>

      <!-- ВЫБЕРИТЕ РОЗЫГРЫШ -->
      <div class="tc-section">
        <p class="tc-section-label">Выберите розыгрыш</p>
        <div class="tc-giveaway-list" id="promo-giveaway-list">
          <div class="tc-loading">Загрузка...</div>
        </div>
      </div>

      <!-- ВРЕМЯ ПУБЛИКАЦИИ — скрыт до выбора розыгрыша -->
      <div class="tc-section tc-section--hidden" id="promo-time-section">
        <p class="tc-section-label">Время публикации в боте</p>
        <div class="tc-period-list" id="promo-time-list">

          <!-- Сразу -->
          <div class="tc-period-card promo-time-card promo-time-card--active"
               data-time-type="immediate" role="button" tabindex="0">
            <div class="tc-period-info">
              <div class="tc-period-label">⚡ Сразу после утверждения</div>
              <div class="tc-period-desc">Не дольше 8 часов</div>
            </div>
            <div class="tc-giveaway-check" id="promo-time-check-immediate">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                      stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
          </div>

          <!-- Выбрать время -->
          <div class="tc-period-card promo-time-card"
               data-time-type="scheduled" role="button" tabindex="0">
            <div class="tc-period-info">
              <div class="tc-period-label">🗓 Выбрать дату и время</div>
              <div class="tc-period-desc" id="promo-scheduled-desc">Нажмите, чтобы указать дату и время</div>
            </div>
            <div class="tc-giveaway-check" id="promo-time-check-scheduled">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
              </svg>
            </div>
          </div>

          <!-- Пикер даты/времени — скрыт до выбора "Выбрать время" -->
          <div class="promo-datetime-picker tc-section--hidden" id="promo-datetime-picker">
            <label class="promo-datetime-label">Дата и время публикации (МСК)</label>
            <input class="promo-datetime-input" type="datetime-local" id="promo-datetime-input" />
            <div class="promo-datetime-hint" id="promo-datetime-hint"></div>
          </div>

        </div>
      </div>

      <!-- СПОСОБ ОПЛАТЫ -->
      <div class="tc-section tc-section--hidden" id="promo-payment-section">
        <p class="tc-section-label">Способ оплаты</p>
        <div class="tc-payment-list">

          <!-- Картой — по умолчанию активна -->
          <div class="tc-payment-card tc-payment-card--active" data-payment="card" role="button" tabindex="0">
            <div class="tc-payment-icon">
              <svg width="22" height="18" viewBox="0 0 22 18" fill="none">
                <rect x="1" y="1" width="20" height="16" rx="3" stroke="currentColor" stroke-width="1.8"/>
                <path d="M1 6h20" stroke="currentColor" stroke-width="1.8"/>
                <rect x="4" y="10" width="4" height="2" rx="1" fill="currentColor"/>
              </svg>
            </div>
            <span class="tc-payment-label">Картой</span>
            <div class="tc-payment-check" id="promo-pay-check-card">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
          </div>

          <!-- Stars -->
          <div class="tc-payment-card" data-payment="stars" role="button" tabindex="0">
            <div class="tc-payment-icon">
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                <path d="M11 2L13.5 8.5L20.5 9L15.5 13.5L17.5 20.5L11 16.5L4.5 20.5L6.5 13.5L1.5 9L8.5 8.5L11 2Z"
                      stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="tc-payment-label">Stars</span>
            <div class="tc-payment-check" id="promo-pay-check-stars">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
              </svg>
            </div>
          </div>

        </div>
      </div>

      <!-- ИТОГО -->
      <div class="tc-section tc-section--hidden" id="promo-summary-section">
        <div class="tc-summary-card">
          <div class="tc-summary-row">
            <span class="tc-summary-label">Продвижение в боте</span>
            <span class="tc-summary-price" id="promo-summary-price">9 990 ₽</span>
          </div>
          <div class="tc-summary-divider"></div>
          <div class="tc-summary-row tc-summary-row--total">
            <span class="tc-summary-label">Итого к оплате</span>
            <span class="tc-summary-price" id="promo-summary-total">9 990 ₽</span>
          </div>
        </div>

        <!-- Согласие с офертой -->
        <div class="tc-agree-block" id="promo-agree-block" role="button" tabindex="0">
          <div class="tc-agree-checkbox" id="promo-agree-checkbox">
            <svg class="tc-agree-check" id="promo-agree-check" width="12" height="10"
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

      <!-- ДИСКЛЕЙМЕР -->
      <div class="tc-disclaimer tc-section--hidden" id="promo-disclaimer">
        <p class="tc-disclaimer-text">
          Услуга оказывается после ручного утверждения администратором PrizeMe.
          Срок рассмотрения — до 8 часов. При оплате услуги вы подтверждаете, что
          ознакомились с
          <a class="tc-disclaimer-link" href="https://prizeme.ru/legal.html?doc=privacy" data-tg-link>политикой конфиденциальности</a>.
          По вопросам возврата и поддержки:
          <a class="tc-disclaimer-link" href="https://t.me/prizeme_support" data-tg-support>@prizeme_support</a>.
        </p>
      </div>

      <div class="svc-bottom-spacer"></div>
    </div>

    <!-- Кнопка «Перейти к оплате» — те же классы что в топ-чекауте -->
    <div class="svc-footer tc-footer--hidden" id="promo-footer-pay">
      <button class="svc-continue-btn tc-pay-btn--inactive" id="promo-pay-btn" type="button">
        Перейти к оплате
      </button>
    </div>
  `;
}
