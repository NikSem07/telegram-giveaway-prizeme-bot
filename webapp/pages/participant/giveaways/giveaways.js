function renderGiveawaysPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">🎯 Мои розыгрыши</h2>
      <p class="stub-text">Здесь появятся ваши активные и прошедшие розыгрыши. Раздел находится в разработке.</p>
    </div>
  `;
}

export {
  renderGiveawaysPage,
};