// webapp/pages/creator/giveaways/giveaway_card_creator.template.js
export default function giveawayCardCreatorTemplate() {
  return `
    <section class="cgcc-screen">
      <!-- Защитный слой фона (аналог участника) -->
      <div class="pgc-background-layer"></div>

      <!-- TOP: заголовок + бейдж -->
      <div class="cgcc-top">
        <div class="cgcc-title" id="cgcc-title">Загрузка...</div>
        <div class="cgcc-badges">
          <div class="cgcc-badge">
            <span class="cgcc-badge-text" id="cgcc-badge-status">⌛ Запущенный</span>
          </div>
          <div class="cgcc-badge">
            <span class="cgcc-badge-text">
              <span id="cgcc-badge-end-label">📅 Дата окончания:</span>
              <span id="cgcc-end">—</span>
            </span>
          </div>
        </div>
      </div>

      <!-- Серый блок «Информация о розыгрыше» -->
      <div class="pgc-frame">
        <!-- Медиа + заголовок блока -->
        <div class="pgc-media-block">
          <div class="pgc-media" id="cgcc-media"></div>
          <div class="pgc-info-title-wrap">
            <div class="pgc-info-title">Информация о розыгрыше</div>
          </div>
        </div>

        <!-- Описание -->
        <div class="pgc-desc">
          <div class="pgc-desc-text" id="cgcc-description"></div>
        </div>

        <!-- Каналы / группы -->
        <div class="pgc-channels">
          <div class="pgc-channels-title">Подключенные каналы / группы к розыгрышу</div>
          <div class="pgc-channels-list" id="cgcc-channels"></div>
        </div>

        <!-- Победители (только для завершённых, скрыт по умолчанию) -->
        <div class="pgc-channels cgcc-winners-block" id="cgcc-winners-wrap" style="display:none">
          <div class="pgc-channels-title">Победители</div>
          <div class="pgc-channels-list" id="cgcc-winners-list"></div>
        </div>
      </div>

      <!-- Отступ под фиксированную кнопку -->
      <div class="pgc-scroll-spacer"></div>
    </section>

    <!-- Фиксированная кнопка «Редактировать» -->
    <div class="pgc-sticky-cta">
      <button class="big_bottom" type="button" id="cgcc-edit">
        Редактировать
      </button>
    </div>
  `;
}
