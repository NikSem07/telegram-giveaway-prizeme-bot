export default function participantGiveawaysTemplate() {
  return `
    <section class="creator-giveaways participant-giveaways">
      <div class="creator-giveaways__tabs" role="tablist" aria-label="Фильтр розыгрышей">
        <button class="creator-giveaways__tab is-active" type="button" data-tab="active" role="tab">Активные</button>
        <button class="creator-giveaways__tab" type="button" data-tab="completed" role="tab">Завершенные</button>
        <button class="creator-giveaways__tab" type="button" data-tab="cancelled" role="tab">Отмененные</button>
      </div>

      <div class="creator-giveaways__total" id="participant-giveaways-total">Всего: 0</div>

      <div class="creator-giveaways__list" id="participant-giveaways-list"></div>
    </section>
  `;
}