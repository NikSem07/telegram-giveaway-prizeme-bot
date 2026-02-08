export default function giveawaysTemplate(context = {}) {
  const { timestamp } = context;

  return `
    <section class="participant-giveaways">
      <header class="participant-giveaways__header">
        <div class="participant-giveaways__title-row">
          <h2 class="participant-giveaways__title">🎯 Мои розыгрыши</h2>
          <div class="participant-giveaways__meta">
            <span class="participant-giveaways__count" id="participant-giveaways-count">Всего: —</span>
          </div>
        </div>

        <nav class="participant-giveaways__tabs" role="tablist" aria-label="Фильтр розыгрышей">
          <button class="participant-giveaways__tab" id="pg-tab-active" data-tab="active" role="tab" aria-selected="false">
            Активные
          </button>
          <button class="participant-giveaways__tab" id="pg-tab-finished" data-tab="finished" role="tab" aria-selected="false">
            Завершенные
          </button>
          <button class="participant-giveaways__tab" id="pg-tab-cancelled" data-tab="cancelled" role="tab" aria-selected="false">
            Отмененные
          </button>
        </nav>
      </header>

      <div class="participant-giveaways__content">
        <div class="participant-giveaways__state" id="participant-giveaways-state" aria-live="polite"></div>
        <div class="participant-giveaways__list" id="participant-giveaways-list"></div>
      </div>

      <div class="participant-giveaways__debug" style="display:none;">${timestamp || ''}</div>
    </section>
  `;
}
