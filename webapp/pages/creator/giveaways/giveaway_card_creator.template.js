// webapp/pages/creator/giveaways/giveaway_card_creator.template.js
export default function giveawayCardCreatorTemplate() {
  return `
    <section class="creator-giveaway-card-detail">
      <div class="creator-giveaway-card-block">
        <div class="creator-giveaway-card-label">Название розыгрыша</div>
        <div class="creator-giveaway-card-box">
          <div class="creator-giveaway-card-text" id="cgcc-title">&lt;Название розыгрыша&gt;</div>
        </div>
      </div>

      <div class="creator-giveaway-card-block">
        <div class="creator-giveaway-card-label">Описание розыгрыша</div>
        <div class="creator-giveaway-card-box">
          <div class="creator-giveaway-card-text" id="cgcc-description">&lt;Описание розыгрыша&gt;</div>
        </div>
      </div>

      <div class="creator-giveaway-card-block creator-giveaway-card-media">
        <div class="creator-giveaway-card-label">Загруженное медиа</div>
        <div class="creator-giveaway-card-media-box" id="cgcc-media"></div>
      </div>

      <div class="creator-giveaway-card-block">
        <div class="creator-giveaway-card-label">Дата окончания розыгрыша</div>
        <div class="creator-giveaway-card-box">
          <div class="creator-giveaway-card-text" id="cgcc-end">&lt;Дата окончания розыгрыша&gt;</div>
        </div>
      </div>

      <div class="creator-giveaway-card-block">
        <div class="creator-giveaway-card-label">Подключенные каналы / группы к розыгрышу</div>
        <div class="creator-giveaway-card-channels" id="cgcc-channels"></div>
      </div>

      <button class="creator-giveaway-card-edit" type="button" id="cgcc-edit">
        <span>Редактировать</span>
        <span class="creator-giveaway-card-edit-icon"></span>
      </button>
    </section>
  `;
}
