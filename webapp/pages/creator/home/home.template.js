// webapp/pages/creator/home/home.template.js
export default function creatorHomeTemplate(context = {}) {
  const total = typeof context.totalGiveaways === 'number' ? context.totalGiveaways : null;

  return `
    <section class="creator-home-v2">

      <div class="creator-home-v2-grid">
        <!-- LEFT COLUMN -->
        <div class="creator-home-v2-left">

          <!-- Total giveaways card -->
          <div class="creator-home-v2-card creator-home-v2-card--total">
            <div class="creator-home-v2-total-text">
              <div class="creator-home-v2-total-line1">Всего проведено</div>
              <div class="creator-home-v2-total-line2">
                <span id="creator-total-giveaways" class="creator-home-v2-total-count">${total !== null ? total : '--'}</span>
                <span class="creator-home-v2-total-word">розыгрыша</span>
              </div>
            </div>
          </div>

          <!-- Donate -->
          <button class="creator-home-v2-card creator-home-v2-card--donate" data-creator-action="donate" type="button">
            <div class="creator-home-v2-card-title">Донат</div>
            <img class="creator-home-v2-arrow" src="/miniapp-static/assets/icons/arrow-icon.svg" alt="arrow" />
          </button>

          <!-- Subscription -->
          <button class="creator-home-v2-card creator-home-v2-card--sub" data-creator-action="subscribe" type="button">
            <div class="creator-home-v2-card-title">Подписка</div>
            <img class="creator-home-v2-arrow" src="/miniapp-static/assets/icons/arrow-icon.svg" alt="arrow" />
          </button>

        </div>

        <!-- RIGHT COLUMN -->
        <button class="creator-home-v2-big" data-creator-action="create" type="button">
          <div class="creator-home-v2-big-title">
            <div>Создать</div>
            <div>новый розыгрыш</div>
          </div>

          <div class="creator-home-v2-plus">
            <img class="creator-home-v2-plus-icon" src="/miniapp-static/assets/icons/plus-icon.svg" alt="plus" />
          </div>

          <img
            class="creator-home-v2-illustration"
            src="/miniapp-static/assets/images/success-image.webp"
            alt="raffle"
          />
        </button>

      </div>
      
      <!-- Блок "Мои каналы" -->
      <div class="ch-section-header">
        <span class="ch-section-title">Мои каналы</span>
        <div class="ch-block-actions">
          <button class="ch-header-btn" type="button" id="ch-refresh-all" title="Обновить все">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          </button>
          <button class="ch-header-btn ch-header-btn--add" type="button" id="ch-add" title="Добавить канал">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
        </div>
      </div>
      <div class="ch-block">
        <div class="ch-list" id="ch-list">
          <div class="ch-loading">Загрузка...</div>
        </div>
      </div>

    </section>
  `;
}
