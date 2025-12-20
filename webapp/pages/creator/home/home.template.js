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
              <div class="creator-home-v2-total-line1">Всего было запущено</div>
              <div class="creator-home-v2-total-line2">
                <span id="creator-total-giveaways" class="creator-home-v2-total-count">${total !== null ? total : '--'}</span>
                <span class="creator-home-v2-total-word">розыгрыша</span>
              </div>
            </div>
          </div>

          <!-- Donate -->
          <button class="creator-home-v2-card creator-home-v2-card--donate" data-creator-action="donate" type="button">
            <div class="creator-home-v2-card-title">Донат проекту</div>
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
            <div>Запустить</div>
            <div>новый розыгрыш</div>
          </div>

          <div class="creator-home-v2-plus">
            <img class="creator-home-v2-plus-icon" src="/miniapp-static/assets/icons/plus-icon.svg" alt="plus" />
          </div>

          <img
            class="creator-home-v2-illustration"
            src="/miniapp-static/assets/images/success-image.svg"
            alt="raffle"
          />
        </button>

      </div>
    </section>
  `;
}
