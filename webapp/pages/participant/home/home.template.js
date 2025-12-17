// webapp/pages/participant/home/home.template.js
export default function homeTemplate(context = {}) {
    const { user = {}, stats = {} } = context;
    const { fullName = 'Друг', firstName = 'Друг' } = user;
    
    return `
        <section class="participant-home">
            <div class="hero-banner">
                <div class="hero-content">
                    <span class="hero-label">УЧАСТНИК</span>
                    <h1>Привет, ${firstName}!</h1>
                    <p class="hero-subtitle">Участвуй в розыгрышах, выполняй задания и выигрывай призы</p>
                </div>
                <div class="hero-decoration">
                    <div class="decoration-item">🎁</div>
                    <div class="decoration-item">🎯</div>
                    <div class="decoration-item">🏆</div>
                </div>
            </div>

            <div class="app-header">
                <h1>🎁 PrizeMe</h1>
                <p class="welcome-text">Платформа розыгрышей в Telegram</p>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">🎯</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.activeGiveaways || 12}</div>
                        <div class="stat-label">Активные розыгрыши</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">✅</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.completedTasks || 5}</div>
                        <div class="stat-label">Выполнено заданий</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">🏆</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.wins || 2}</div>
                        <div class="stat-label">Побед</div>
                    </div>
                </div>
            </div>

            <div class="action-section">
                <h2 class="section-title">Быстрые действия</h2>
                <div class="action-grid">
                    <button class="action-card" data-action="participate">
                        <div class="action-icon">🚀</div>
                        <div class="action-text">
                            <div class="action-title">Участвовать</div>
                            <div class="action-subtitle">В активных розыгрышах</div>
                        </div>
                    </button>
                    <button class="action-card" data-action="tasks">
                        <div class="action-icon">📋</div>
                        <div class="action-text">
                            <div class="action-title">Задания</div>
                            <div class="action-subtitle">Для участия</div>
                        </div>
                    </button>
                    <button class="action-card" data-action="my-giveaways">
                        <div class="action-icon">🎯</div>
                        <div class="action-text">
                            <div class="action-title">Мои розыгрыши</div>
                            <div class="action-subtitle">Активные и прошлые</div>
                        </div>
                    </button>
                    <button class="action-card" data-action="profile">
                        <div class="action-icon">👤</div>
                        <div class="action-text">
                            <div class="action-title">Профиль</div>
                            <div class="action-subtitle">Настройки и прогресс</div>
                        </div>
                    </button>
                </div>
            </div>
        </section>
    `;
}
