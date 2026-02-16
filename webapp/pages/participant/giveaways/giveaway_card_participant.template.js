// webapp/pages/participant/giveaways/giveaway_card_participant.template.js
export default function giveawayCardParticipantTemplate() {
  return `
    <section class="pgc-screen">
      <!-- Защитный слой для гарантии отсутствия зазоров -->
      <div class="pgc-background-layer"></div>
      
      <!-- TOP: title + badges -->
      <div class="pgc-top">
        <div class="pgc-top-title-wrap">
          <div class="pgc-title" id="pgc-title">&lt;Название розыгрыша&gt;</div>
        </div>

        <div class="pgc-badges">
          <div class="pgc-badge pgc-badge--status">
            <span class="pgc-badge-text" id="pgc-badge-status">⌛ Активный</span>
          </div>

          <div class="pgc-badge pgc-badge--left">
            <span class="pgc-badge-text">
              <span id="pgc-badge-secondary-label">🕒 Осталось:</span>
              <span id="pgc-left-time">—</span>
            </span>
          </div>

          <div class="pgc-badge pgc-badge--winners">
            <span class="pgc-badge-text" id="pgc-badge-winner">🤷 Победители не определены</span>
          </div>
        </div>
      </div>

      <!-- Tickets -->
      <div class="pgc-tickets">
        <div class="pgc-tickets-title"><span class="pgc-text-10">Ваши билеты</span></div>
        <div class="pgc-tickets-list" id="pgc-tickets-list"></div>
      </div>

      <!-- Bottom content frame с кнопкой внутри -->
      <div class="pgc-frame">
        <!-- Media + title -->
        <div class="pgc-media-block">
          <div class="pgc-media" id="pgc-media"></div>
          <div class="pgc-info-title-wrap">
            <div class="pgc-info-title">Информация о розыгрыше</div>
          </div>
        </div>

        <!-- Description -->
        <div class="pgc-desc">
          <div class="pgc-desc-text" id="pgc-description"></div>
        </div>

        <!-- Channels -->
        <div class="pgc-channels">
          <div class="pgc-channels-title">Подключенные каналы / группы к розыгрышу</div>
          <div class="pgc-channels-list" id="pgc-channels"></div>
        </div>

      </div>

      <!-- CTA: кнопка вынесена ИЗ серого блока -->
      <div class="pgc-cta">
        <button class="big_bottom" type="button" id="pgc-open">
          Перейти к розыгрышу
        </button>
      </div>
    </section>
  `;
}
