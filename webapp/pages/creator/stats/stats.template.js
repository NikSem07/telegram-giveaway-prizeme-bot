// webapp/pages/creator/stats/stats.template.js

export function statsOverviewTemplate() {
    return `
        <div class="stats-page" id="stats-overview-page">
            <div class="stats-header">
                <div class="stats-header-title">📊 Статистика</div>
                <div class="stats-header-sub">Аналитика по всем розыгрышам</div>
            </div>

            <!-- KPI карточки -->
            <div class="stats-kpi-grid" id="stats-kpi-grid">
                <div class="stats-kpi-card" style="--kpi-accent:#007AFF">
                    <span class="stats-kpi-icon">🎟</span>
                    <div class="stats-kpi-value" id="kpi-total-entries">—</div>
                    <div class="stats-kpi-label">Участников</div>
                </div>
                <div class="stats-kpi-card" style="--kpi-accent:#34C759">
                    <span class="stats-kpi-icon">🚀</span>
                    <div class="stats-kpi-value" id="kpi-active">—</div>
                    <div class="stats-kpi-label">Активных</div>
                </div>
                <div class="stats-kpi-card" style="--kpi-accent:#FF9500">
                    <span class="stats-kpi-icon">🏆</span>
                    <div class="stats-kpi-value" id="kpi-total-gw">—</div>
                    <div class="stats-kpi-label">Розыгрышей</div>
                </div>
                <div class="stats-kpi-card" style="--kpi-accent:#FF2D55">
                    <span class="stats-kpi-icon">✅</span>
                    <div class="stats-kpi-value" id="kpi-finished">—</div>
                    <div class="stats-kpi-label">Завершено</div>
                </div>
            </div>

            <!-- График трендов -->
            <div class="stats-section">
                <div class="stats-section-label">Рост участников</div>
                <div class="stats-chart-wrap">
                    <div class="stats-chart-header">
                        <div class="stats-chart-title">За последние 30 дней</div>
                    </div>
                    <div class="stats-chart-canvas-wrap">
                        <canvas id="stats-overview-chart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Список розыгрышей -->
            <div class="stats-section">
                <div class="stats-section-label">Розыгрыши</div>
                <div class="stats-giveaway-list" id="stats-giveaway-list">
                    <div class="stats-loading">
                        <div class="stats-spinner"></div>
                        <div class="stats-loading-text">Загрузка...</div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

export function statsDetailTemplate(giveaway) {
    const statusLabel = { active: 'Активен', finished: 'Завершён', draft: 'Черновик' };
    const statusClass = { active: 'active', finished: 'finished', draft: 'draft' };
    const s = giveaway.status || 'draft';
    return `
        <div class="stats-detail-page" id="stats-detail-page">
            <!-- Хедер розыгрыша -->
            <div class="stats-header">
                <div class="stats-detail-header">
                    <div class="stats-detail-avatar" id="stats-detail-avatar">🎁</div>
                    <div class="stats-detail-info">
                        <div class="stats-detail-title">${_esc(giveaway.internal_title)}</div>
                        <div class="stats-detail-sub">
                            <span class="stats-giveaway-status-badge stats-giveaway-status-badge--${statusClass[s] || 'draft'}">
                                ${statusLabel[s] || s}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Большие метрики -->
            <div class="stats-big-metrics" id="stats-big-metrics">
                <div class="stats-big-metric">
                    <div class="stats-big-metric-value" id="dm-participants">—</div>
                    <div class="stats-big-metric-label">Участников</div>
                </div>
                <div class="stats-big-metric">
                    <div class="stats-big-metric-value" id="dm-clicks">—</div>
                    <div class="stats-big-metric-label">Кликов</div>
                </div>
                <div class="stats-big-metric">
                    <div class="stats-big-metric-value" id="dm-conversion">—</div>
                    <div class="stats-big-metric-label">Конверсия</div>
                </div>
            </div>

            <!-- График участников -->
            <div class="stats-section">
                <div class="stats-section-label">Динамика участников</div>
                <div class="stats-chart-wrap">
                    <div class="stats-chart-header">
                        <div class="stats-chart-title" id="detail-chart-title">По часам</div>
                        <div class="stats-chart-tabs">
                            <button class="stats-chart-tab stats-chart-tab--active" data-period="hourly">7 дней</button>
                            <button class="stats-chart-tab" data-period="daily">Всё</button>
                        </div>
                    </div>
                    <div class="stats-chart-canvas-wrap">
                        <canvas id="stats-detail-chart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Воронка -->
            <div class="stats-section">
                <div class="stats-section-label">Воронка участия</div>
                <div class="stats-card">
                    <div class="stats-funnel" id="stats-funnel">
                        <div class="stats-loading"><div class="stats-spinner"></div></div>
                    </div>
                </div>
            </div>

            <!-- Источники -->
            <div class="stats-section">
                <div class="stats-section-label">Источники участников</div>
                <div class="stats-card">
                    <div class="stats-sources-list" id="stats-sources-list">
                        <div class="stats-loading"><div class="stats-spinner"></div></div>
                    </div>
                </div>
            </div>

            <!-- Новые подписчики -->
            <div class="stats-section" id="stats-newsubs-section">
                <div class="stats-section-label">Новые подписчики</div>
                <div class="stats-card">
                    <div class="stats-newsubs-list" id="stats-newsubs-list">
                        <div class="stats-loading"><div class="stats-spinner"></div></div>
                    </div>
                </div>
            </div>

            <!-- Аудитория -->
            <div class="stats-section">
                <div class="stats-section-label">Аудитория</div>
                <div class="stats-audience-grid">
                    <div class="stats-donut-card">
                        <div class="stats-donut-title">Telegram Premium</div>
                        <div class="stats-donut-wrap">
                            <canvas id="donut-premium"></canvas>
                            <div class="stats-donut-center">
                                <div class="stats-donut-center-value" id="donut-premium-pct">—</div>
                                <div class="stats-donut-center-label">Premium</div>
                            </div>
                        </div>
                        <div class="stats-donut-legend" id="donut-premium-legend"></div>
                    </div>
                    <div class="stats-donut-card">
                        <div class="stats-donut-title">Языки</div>
                        <div class="stats-donut-wrap">
                            <canvas id="donut-langs"></canvas>
                            <div class="stats-donut-center">
                                <div class="stats-donut-center-value" id="donut-langs-top">—</div>
                                <div class="stats-donut-center-label">Топ язык</div>
                            </div>
                        </div>
                        <div class="stats-donut-legend" id="donut-langs-legend"></div>
                    </div>
                </div>
            </div>

            <!-- Языки / география подробно -->
            <div class="stats-section">
                <div class="stats-section-label">География аудитории</div>
                <div class="stats-card">
                    <div class="stats-lang-list" id="stats-lang-list">
                        <div class="stats-loading"><div class="stats-spinner"></div></div>
                    </div>
                </div>
            </div>

            <!-- Финансы -->
            <div class="stats-section" id="stats-finance-section">
                <div class="stats-section-label">Расходы на сервисы</div>
                <div class="stats-card">
                    <div class="stats-finance-rows" id="stats-finance-rows">
                        <div class="stats-loading"><div class="stats-spinner"></div></div>
                    </div>
                </div>
            </div>

            <!-- Победители (если завершён) -->
            <div class="stats-section" id="stats-winners-section" style="display:none">
                <div class="stats-section-label">Победители</div>
                <div class="stats-card">
                    <div class="stats-winners-list" id="stats-winners-list"></div>
                </div>
            </div>

        </div>
    `;
}

function _esc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
