// Контент для главной создателя
function getCreatorHomeContent() {
  return `
    <div class="card">
      <div class="app-header">
        <h1>🎁 PrizeMe Creator</h1>
        <p class="welcome-text">Панель управления розыгрышами</p>
      </div>
      
      <div class="menu-grid">
        <button class="menu-btn primary" onclick="createGiveaway()">
          <span class="btn-icon">➕</span>
          <span class="btn-text">Создать розыгрыш</span>
        </button>
        
        <button class="menu-btn secondary" onclick="showMyGiveaways()">
          <span class="btn-icon">📋</span>
          <span class="btn-text">Мои розыгрыши</span>
        </button>
        
        <button class="menu-btn secondary" onclick="showStatistics()">
          <span class="btn-icon">📊</span>
          <span class="btn-text">Статистика</span>
        </button>
      </div>
      
      <div class="stats-section">
        <div class="stat-item">
          <span class="stat-number" id="active-giveaways">0</span>
          <span class="stat-label">активных</span>
        </div>
        <div class="stat-item">
          <span class="stat-number" id="total-participants">0</span>
          <span class="stat-label">участников</span>
        </div>
        <div class="stat-item">
          <span class="stat-number" id="completed-giveaways">0</span>
          <span class="stat-label">завершено</span>
        </div>
      </div>
    </div>
  `;
}

function renderHomePage() {
  const mainContent = document.getElementById('main-content');
  mainContent.innerHTML = getCreatorHomeContent();
  loadCreatorStats(); // важно: на home должна обновляться статистика
}


// Загрузка статистики создателя
function loadCreatorStats() {
  setTimeout(() => {
    const activeElement = document.getElementById('active-giveaways');
    const participantsElement = document.getElementById('total-participants');
    const completedElement = document.getElementById('completed-giveaways');
    
    if (activeElement) activeElement.textContent = '3';
    if (participantsElement) participantsElement.textContent = '156';
    if (completedElement) completedElement.textContent = '12';
  }, 500);
}

export { renderHomePage };
