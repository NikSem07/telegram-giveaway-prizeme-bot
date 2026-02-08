export default function giveawaysTemplate(context = {}) {
  const { timestamp } = context;

  return `
    <section class="creator-giveaways participant-giveaways">
      <!-- Tabs: сохраняем селектор .participant-giveaways__tab для JS,
           но добавляем creator-классы для 1:1 дизайна -->
      <div class="creator-giveaways__tabs participant-giveaways__tabs" role="tablist" aria-label="Фильтр розыгрышей">
        <button
          class="creator-giveaways__tab participant-giveaways__tab is-active"
          type="button"
          data-tab="active"
          role="tab"
          aria-selected="true"
        >Активные</button>

        <!-- ВАЖНО: data-tab="finished", а не completed, потому что JS ждёт finished -->
        <button
          class="creator-giveaways__tab participant-giveaways__tab"
          type="button"
          data-tab="finished"
          role="tab"
          aria-selected="false"
        >Завершенные</button>

        <button
          class="creator-giveaways__tab participant-giveaways__tab"
          type="button"
          data-tab="cancelled"
          role="tab"
          aria-selected="false"
        >Отмененные</button>
      </div>

      <!-- Count: JS обновляет #participant-giveaways-count -->
      <div class="creator-giveaways__total participant-giveaways__count" id="participant-giveaways-count">Всего: —</div>

      <!-- State: JS пишет сюда "Загрузка…" / ошибки / пустые состояния -->
      <div class="participant-giveaways__state" id="participant-giveaways-state" aria-live="polite"></div>

      <!-- List: JS ожидает #participant-giveaways-list -->
      <div class="creator-giveaways__list participant-giveaways__list" id="participant-giveaways-list"></div>

      <div class="participant-giveaways__debug" style="display:none;">${timestamp || ''}</div>
    </section>
  `;
}
