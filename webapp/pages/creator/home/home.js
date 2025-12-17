// \webapp\pages\creator\home\home.js

export function renderCreatorHomePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <section class="creator-home">
      <div class="creator-hero">
        <div class="creator-hero-title">
          <span class="creator-hero-label">СОЗДАТЕЛЬ</span>
          <h2>Управление розыгрышами</h2>
        </div>
      </div>

      <div class="app-header">
        <h1>🎁 PrizeMe Creator</h1>
        <p class="welcome-text">Панель управления розыгрышами</p>
      </div>

      <div class="creator-actions">
        <div class="creator-action-card" data-creator-action="create">
          <div class="creator-action-icon">➕</div>
          <div class="creator-action-text">
            <div class="creator-action-title">Создать розыгрыш</div>
            <div class="creator-action-subtitle">Запуск нового розыгрыша</div>
          </div>
        </div>

        <div class="creator-action-card" data-creator-action="my">
          <div class="creator-action-icon">📋</div>
          <div class="creator-action-text">
            <div class="creator-action-title">Мои розыгрыши</div>
            <div class="creator-action-subtitle">Активные и завершённые</div>
          </div>
        </div>

        <div class="creator-action-card" data-creator-action="stats">
          <div class="creator-action-icon">📊</div>
          <div class="creator-action-text">
            <div class="creator-action-title">Статистика</div>
            <div class="creator-action-subtitle">Участники и результаты</div>
          </div>
        </div>
      </div>
    </section>
  `;

  // Ненавязчиво: если у тебя где-то уже есть функции - используем их
  main.querySelector('[data-creator-action="create"]')?.addEventListener('click', () => {
    window.createGiveaway?.();
  });
  main.querySelector('[data-creator-action="my"]')?.addEventListener('click', () => {
    window.showMyGiveaways?.();
  });
  main.querySelector('[data-creator-action="stats"]')?.addEventListener('click', () => {
    window.showStatistics?.();
  });
}
