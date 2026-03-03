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
    const badgeColors = {
        active:    'background:rgba(52,199,89,0.18);color:#34C759;border:1px solid rgba(52,199,89,0.35)',
        finished:  'background:rgba(255,59,48,0.18);color:#FF453A;border:1px solid rgba(255,59,48,0.35)',
        draft:     'background:rgba(255,149,0,0.18);color:#FF9F0A;border:1px solid rgba(255,149,0,0.35)',
        cancelled: 'background:rgba(255,59,48,0.15);color:#FF453A;border:1px solid rgba(255,59,48,0.3)',
    };
    const endTs   = g.end_at_utc || g.ended_at || null;
    const endedAt = endTs ? new Date(endTs).toLocaleString('ru-RU', {
        day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'
    }) : null;
    const timeBadge = s === 'active'
        ? `<span class="st-detail-badge" id="detail-timer-badge" style="background:rgba(0,122,255,0.15);color:#007AFF;border:1px solid rgba(0,122,255,0.3)">⏱ <span id="detail-timer">...</span></span>`
        : endedAt
            ? `<span class="st-detail-badge" style="background:rgba(255,255,255,0.06);color:var(--color-text-secondary);border:1px solid rgba(255,255,255,0.1)">${endedAt}</span>`
            : '';
    return `
<div class="st-detail" id="st-detail-page">
    <div class="st-detail-head">
        <div class="st-detail-title">${_esc(g.internal_title)}</div>
        <div class="st-detail-badges">
            <span class="st-detail-badge" style="${badgeColors[s]||badgeColors.draft}">${STATUS_LABEL[s]||s}</span>
            ${timeBadge}
        </div>
    </div>

    <div class="st-m3">
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-parts">—</div>
            <div class="st-m3-lbl" id="dm-parts-lbl">УЧАСТНИКОВ</div>
        </div>
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-clicks">—</div>
            <div class="st-m3-lbl" id="dm-clicks-lbl">КЛИКОВ</div>
        </div>
        <div class="st-m3-card">
            <div class="st-m3-val" id="dm-conv">—</div>
            <div class="st-m3-lbl">КОНВЕРСИЯ</div>
        </div>
        <div class="st-m3-card st-m3-card--csv" id="dm-csv-btn" data-gid="${_esc(String(g.id))}">
            <img src="/miniapp-static/assets/icons/download-icon.svg"
                 style="width:22px;height:22px;filter:brightness(10);margin-bottom:4px"
                 alt="CSV">
            <div class="st-m3-lbl" style="color:#fff">CSV</div>
        </div>
    </div>

    <div class="st-csv-modal" id="st-csv-modal" style="display:none">
        <div class="st-csv-backdrop" id="st-csv-backdrop"></div>
        <div class="st-csv-sheet">
            <div class="st-csv-title">Хотите выгрузить CSV файл?</div>
            <div class="st-csv-desc">Бот вышлет CSV файл со статистикой, вы также сможете вернуться обратно в приложение</div>
            <div class="st-csv-btns">
                <button class="st-csv-btn st-csv-btn--cancel" id="st-csv-cancel">Отмена</button>
                <button class="st-csv-btn st-csv-btn--confirm" id="st-csv-confirm">Да</button>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Динамика участников</div>
        <div class="st-chart-card">
            <div class="st-chart-body" id="detail-chart-body">
                <canvas id="detail-chart"></canvas>
            </div>
            <div class="st-chart-controls">
                <div class="st-chart-ctrl-lbl">Период</div>
                <div class="st-chart-btns" id="chart-period-btns">
                    <button class="st-chart-btn st-chart-btn--on" data-period="all">Все</button>
                    <button class="st-chart-btn" data-period="24h">24 часа</button>
                    <button class="st-chart-btn" data-period="7d">7 дней</button>
                    <button class="st-chart-btn" data-period="30d">30 дней</button>
                </div>
                <div class="st-chart-ctrl-lbl" style="margin-top:10px">Группировка</div>
                <div class="st-chart-btns" id="chart-group-btns">
                    <button class="st-chart-btn st-chart-btn--on" data-group="hourly">По часам</button>
                    <button class="st-chart-btn" data-group="daily">По дням</button>
                </div>
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

    <div class="st-section">
        <div class="st-section-lbl">Статус в Telegram</div>
        <div class="st-card">
            <div class="st-aud-full" id="st-aud-premium">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

    <div class="st-section">
        <div class="st-section-lbl">Участники по языкам</div>
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

    <div class="st-section" id="newsubs-section">
        <div class="st-section-lbl">Новые подписчики</div>
        <div class="st-card">
            <div class="st-newsubs" id="st-newsubs">
                <div class="st-mini-loading"><div class="st-spinner"></div></div>
            </div>
        </div>
    </div>

</div>`;
}

function _esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
