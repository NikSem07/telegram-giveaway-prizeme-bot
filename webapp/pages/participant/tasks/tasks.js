function renderTasksPage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  main.innerHTML = `
    <div class="stub-card">
      <h2 class="stub-title">📋 Задания</h2>
      <p class="stub-text">Выполняйте задания, чтобы участвовать в розыгрышах. Раздел находится в разработке.</p>
    </div>
  `;
}

export {
  renderTasksPage,
};