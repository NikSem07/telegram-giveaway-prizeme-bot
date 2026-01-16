// webapp/pages/creator/giveaways/giveaways.template.js
export default function creatorGiveawaysTemplate() {
  return `
    <section class="creator-giveaways">
      <div class="creator-giveaways__tabs" role="tablist" aria-label="Фильтр розыгрышей">
        <button class="creator-giveaways__tab is-active" type="button" data-tab="active" role="tab">Запущенные</button>
        <button class="creator-giveaways__tab" type="button" data-tab="draft" role="tab">Незапущенные</button>
        <button class="creator-giveaways__tab" type="button" data-tab="completed" role="tab">Завершенные</button>
      </div>

      <div class="creator-giveaways__total" id="creator-giveaways-total">Всего: 0</div>

      <div class="creator-giveaways__list" id="creator-giveaways-list"></div>
    </section>
  `;
}
