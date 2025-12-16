// Контент для сервисов создателя
function getCreatorServicesContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>🛠️ Сервисы</h1>
        <p class="welcome-text">Дополнительные инструменты</p>
      </div>
      
      <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 64px; margin-bottom: 20px;">🚧</div>
        <h2>Скоро будет доступно</h2>
        <p>Раздел находится в разработке</p>
      </div>
    </div>
  `;
}

function renderServicesPage() {
  const mainContent = document.getElementById('main-content');
  mainContent.innerHTML = getCreatorServicesContent();
}

export { renderServicesPage };
