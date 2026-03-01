// webapp/pages/creator/services/promotion-services.template.js

export default function promotionCheckoutTemplate() {
  return `
    <div class="tc-screen" id="promo-checkout-screen">

      <!-- Заголовок -->
      <div class="tc-header">
        <h1 class="tc-title">📣 Продвижение в боте</h1>
        <p class="tc-subtitle">Розыгрыш будет опубликован в боте — все пользователи получат уведомление с возможностью принять участие</p>
      </div>

      <!-- ВЫБЕРИТЕ РОЗЫГРЫШ -->
      <div class="tc-section">
        <div class="tc-section-label">ВЫБЕРИТЕ РОЗЫГРЫШ</div>
        <div class="tc-giveaway-list" id="promo-giveaway-list">
          <div class="tc-loading">Загрузка...</div>
        </div>
      </div>

      <!-- ВРЕМЯ ПУБЛИКАЦИИ — скрыто до выбора розыгрыша -->
      <div class="tc-section tc-section--hidden" id="promo-time-section">
        <div class="tc-section-label">ВРЕМЯ ПУБЛИКАЦИИ В БОТЕ</div>
        <div class="tc-period-list" id="promo-time-list">

          <!-- Сразу -->
          <div class="tc-period-card promo-time-card promo-time-card--active"
               data-time-type="immediate" role="button" tabindex="0">
            <div class="tc-period-info">
              <div class="tc-period-name">⚡ Сразу после утверждения</div>
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
              <div class="tc-period-name">🗓 Выбрать время</div>
              <div class="tc-period-desc" id="promo-scheduled-desc">Укажите дату и время публикации</div>
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
          </div>

        </div>
      </div>

      <!-- СПОСОБ ОПЛАТЫ — скрыт до выбора времени -->
      <div class="tc-section tc-section--hidden" id="promo-payment-section">
        <div class="tc-section-label">СПОСОБ ОПЛАТЫ</div>
        <div class="tc-payment-list">

          <div class="tc-payment-card tc-payment-card--active" data-payment="stars" role="button" tabindex="0">
            <div class="tc-payment-icon">⭐</div>
            <div class="tc-payment-label">Telegram Stars</div>
            <div class="tc-payment-check" id="promo-pay-check-stars">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="9" fill="#007AFF"/>
                <path d="M5 9L7.5 11.5L13 6" stroke="white" stroke-width="1.8"
                      stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
          </div>

          <div class="tc-payment-card" data-payment="card" role="button" tabindex="0">
            <div class="tc-payment-icon">💳</div>
            <div class="tc-payment-label">Картой</div>
            <div class="tc-payment-check" id="promo-pay-check-card">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="8.5" stroke="rgba(255,255,255,0.2)"/>
              </svg>
            </div>
          </div>

        </div>
      </div>

      <!-- ИТОГО — скрыт до выбора времени -->
      <div class="tc-section tc-section--hidden" id="promo-summary-section">
        <div class="tc-summary-card">
          <div class="tc-summary-row">
            <span class="tc-summary-label">Продвижение в боте</span>
            <span class="tc-summary-price" id="promo-summary-price">500 ⭐</span>
          </div>
          <div class="tc-summary-divider"></div>
          <div class="tc-summary-row tc-summary-row--total">
            <span class="tc-summary-label">Итого к оплате</span>
            <span class="tc-summary-price" id="promo-summary-total">500 ⭐</span>
          </div>
        </div>
      </div>

      <!-- СОГЛАСИЕ С ОФЕРТОЙ — скрыто до выбора времени -->
      <div class="tc-section tc-section--hidden" id="promo-agree-section">
        <div class="tc-agree-block" id="promo-agree-block">
          <div class="tc-agree-checkbox" id="promo-agree-checkbox">
            <svg id="promo-agree-check" width="14" height="14" viewBox="0 0 14 14"
                 fill="none" style="display:none">
              <path d="M2.5 7L5.5 10L11.5 4" stroke="white" stroke-width="2"
                    stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <p class="tc-agree-text">
            Я ознакомлен с
            <a class="tc-legal-link" href="https://prizeme.ru/offer" target="_blank"
               data-tg-link>офертой</a>
            и
            <a class="tc-legal-link" href="https://prizeme.ru/privacy" target="_blank"
               data-tg-link>соглашением</a>
          </p>
        </div>
      </div>

      <!-- ДИСКЛЕЙМЕР — скрыт до выбора времени -->
      <div class="tc-section tc-disclaimer tc-section--hidden" id="promo-disclaimer">
        <p class="tc-disclaimer-text">
          Услуга оказывается после ручного утверждения администратором PrizeMe.
          Срок рассмотрения — до 8 часов. Возврат средств осуществляется в соответствии с
          <a class="tc-disclaimer-link" href="https://prizeme.ru/offer" target="_blank"
             data-tg-link>офертой</a>.
          По вопросам обращайтесь:
          <a class="tc-disclaimer-link" href="https://t.me/prizeme_support"
             data-tg-support>@prizeme_support</a>.
        </p>
      </div>

      <div class="tc-bottom-spacer"></div>
    </div>

    <!-- Кнопка оплаты -->
    <div class="tc-footer tc-footer--hidden" id="promo-footer-pay">
      <button class="tc-pay-btn tc-pay-btn--inactive" id="promo-pay-btn" type="button">
        Перейти к оплате
      </button>
    </div>
  `;
}
