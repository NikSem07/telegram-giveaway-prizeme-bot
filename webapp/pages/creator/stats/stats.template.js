// webapp/pages/creator/stats/stats.template.js

const STATUS_LABEL = { active: 'Активен', finished: 'Завершён', draft: 'Черновик', cancelled: 'Отменён' };
const STATUS_CLS   = { active: 'active', finished: 'finished', draft: 'draft', cancelled: 'cancelled' };

export function statsOverviewTemplate() {
    return `
<div class="stats-page" id="stats-overview-page">
    <div class="st-header">
        <div class="st-lottie-wrap" id="st-lottie-wrap"></div>
        <div class="st-title">Статистика</div>
        <div class="st-subtitle">В разделе общая статистика по всем розыгрышам, ниже можете выбрать конкретный розыгрыш</div>
    </div>

    <div class="st-kpi-row">
        <div class="st-kpi" style="--st-kpi-color:#007AFF">
            <span class="st-kpi-emoji">🎟</span>
            <div class="st-kpi-val" id="kpi-participants">—</div>
            <div class="st-kpi-lbl">Билетов</div>
        </div>
        <div class="st-kpi" style="--st-kpi-color:#FF9500">
            <span class="st-kpi-emoji">🏆</span>
            <div class="st-kpi-val" id="kpi-total">—</div>
            <div class="st-kpi-lbl">Розыгрышей</div>
        </div>
        <div class="st-kpi" style="--st-kpi-color:#34C759">
            <span class="st-kpi-emoji">🚀</span>
            <div class="st-kpi-val" id="kpi-active">—</div>
            <div class="st-kpi-lbl">Активных</div>
        </div>
        <div class="st-kpi" style="--st-kpi-color:#FF2D55">
            <span class="st-kpi-emoji">✅</span>
            <div class="st-kpi-val" id="kpi-finished">—</div>
            <div class="st-kpi-lbl">Завершенных</div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Мои розыгрыши</div>
        <div class="st-filters" id="st-filters">
            <button class="st-filter-btn st-filter-btn--on" data-filter="all">Все</button>
            <button class="st-filter-btn" data-filter="active">Активные</button>
            <button class="st-filter-btn" data-filter="finished">Завершенные</button>
        </div>
        <div class="st-gw-list" id="st-gw-list">
            <div class="st-loading">
                <div class="st-spinner"></div>
                <div class="st-loading-txt">Загрузка...</div>
            </div>
        </div>
    </div>
</div>`;
}

export function statsDetailTemplate(g) {
    const s = g.status || 'draft';
    return `
<div class="st-detail" id="st-detail-page">
    <div class="st-detail-head">
        <div class="st-detail-ava" id="detail-ava">🎁</div>
        <div class="st-detail-info">
            <div class="st-detail-title">${_esc(g.internal_title)}</div>
            <span class="st-badge st-badge--${STATUS_CLS[s]||'draft'}">${STATUS_LABEL[s]||s}</span>
        </div>
    </div>

    <div class="st-m3">
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-parts">—</div>
            <div class="st-m3-lbl">Участников</div>
        </div>
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-clicks">—</div>
            <div class="st-m3-lbl">Кликов</div>
        </div>
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-conv">—</div>
            <div class="st-m3-lbl">Конверсия</div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Динамика участников</div>
        <div class="st-chart-card">
            <div class="st-chart-head">
                <div class="st-chart-ttl" id="detail-chart-ttl">По часам (7 дней)</div>
                <div class="st-tabs">
                    <button class="st-tab st-tab--on" data-period="hourly">7 дн</button>
                    <button class="st-tab" data-period="daily">Всё</button>
                </div>
            </div>
            <div class="st-chart-body" id="detail-chart-body">
                <canvas id="detail-chart"></canvas>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Воронка участия</div>
        <div class="st-card">
            <div class="st-funnel" id="st-funnel">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Источники участников</div>
        <div class="st-card">
            <div class="st-sources" id="st-sources">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

    <div class="st-section" id="newsubs-section">
        <div class="st-section-lbl">Новые подписчики</div>
        <div class="st-card">
            <div class="st-newsubs" id="st-newsubs">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Аудитория</div>
        <div class="st-aud-row">
            <div class="st-donut-card">
                <div class="st-donut-ttl">Telegram Premium</div>
                <div class="st-donut-wrap">
                    <canvas id="donut-premium"></canvas>
                    <div class="st-donut-center">
                        <div class="st-donut-big" id="donut-premium-val">—</div>
                        <div class="st-donut-sub">Premium</div>
                    </div>
                </div>
                <div class="st-donut-legend" id="donut-premium-leg"></div>
            </div>
            <div class="st-donut-card">
                <div class="st-donut-ttl">Языки</div>
                <div class="st-donut-wrap">
                    <canvas id="donut-langs"></canvas>
                    <div class="st-donut-center">
                        <div class="st-donut-big" id="donut-langs-val">—</div>
                        <div class="st-donut-sub">Топ</div>
                    </div>
                </div>
                <div class="st-donut-legend" id="donut-langs-leg"></div>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">География аудитории</div>
        <div class="st-card">
            <div class="st-langs" id="st-langs">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

    <div class="st-section" id="finance-section" style="display:none">
        <div class="st-section-lbl">Расходы на сервисы</div>
        <div class="st-card">
            <div class="st-fin" id="st-fin"></div>
        </div>
    </div>

    <div class="st-section" id="winners-section" style="display:none">
        <div class="st-section-lbl">🏆 Победители</div>
        <div class="st-card">
            <div class="st-wins" id="st-wins"></div>
        </div>
    </div>
</div>`;
}

function _esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
