// webapp/pages/participant/giveaways/giveaway_card_participant.template.js
export default function giveawayCardParticipantTemplate() {
  return `
    <section class="participant-giveaway-card">

      <!-- Верх: название + статусы -->
      <div class="pgc-top">
        <div class="pgc-title" id="pgc-title">&lt;Название розыгрыша&gt;</div>

        <div class="pgc-badges">
          <div class="pgc-badge">⏳ Активный</div>
          <div class="pgc-badge">🤷 Победители не определены</div>
          <div class="pgc-badge" id="pgc-left">🕒 Осталось: —</div>
        </div>
      </div>

      <!-- Ваши билеты -->
      <div class="pgc-tickets">
        <div class="pgc-tickets-title">Ваши билеты</div>
        <div class="pgc-tickets-list" id="pgc-tickets-list"></div>
      </div>

      <!-- Нижний серый блок -->
      <div class="pgc-bottom">
        <div class="pgc-info-title">Информация о розыгрыше</div>

        <div class="pgc-media" id="pgc-media"></div>

        <div class="pgc-description" id="pgc-description">
          &lt;Текст описания розыгрыша&gt;
        </div>

        <div class="pgc-channels-title">Подключенные каналы / группы к розыгрышу</div>
        <div class="pgc-channels" id="pgc-channels"></div>

        <button class="big_bottom" type="button" id="pgc-open">
          Перейти к розыгрышу
        </button>
      </div>
    </section>
  `;
}
