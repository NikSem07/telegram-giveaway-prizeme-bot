// webapp/pages/creator/stats/stats.js
import { statsOverviewTemplate, statsDetailTemplate } from './stats.template.js';

// ── Состояние ─────────────────────────────────────────────────────────────
let _currentView  = 'overview'; // 'overview' | 'detail'
let _detailData   = null;
let _overviewData = null;
let _chartInstances = {};        // Chart.js инстансы — уничтожаем перед пересозданием

// ── Утилиты ───────────────────────────────────────────────────────────────
function getInitData() {
    return window.Telegram?.WebApp?.initData
        || sessionStorage.getItem('prizeme_init_data') || '';
}

function fmt(n) {
    if (n === null || n === undefined || n === '') return '—';
    const num = Number(n);
    if (!isFinite(num)) return '—';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 10000)   return (num / 1000).toFixed(0) + 'K';
    if (num >= 1000)    return (num / 1000).toFixed(1) + 'K';
    return num.toLocaleString('ru-RU');
}

function pct(a, b) {
    if (!b || b === 0) return '0%';
    return Math.round((a / b) * 100) + '%';
}

function destroyChart(id) {
    if (_chartInstances[id]) {
        try { _chartInstances[id].destroy(); } catch (e) {}
        delete _chartInstances[id];
    }
}

// ── Флаги языков ──────────────────────────────────────────────────────────
const LANG_FLAGS = {
    ru: '🇷🇺', en: '🇬🇧', uk: '🇺🇦', kk: '🇰🇿', be: '🇧🇾',
    de: '🇩🇪', fr: '🇫🇷', es: '🇪🇸', it: '🇮🇹', tr: '🇹🇷',
    pt: '🇵🇹', pl: '🇵🇱', ar: '🇸🇦', zh: '🇨🇳', ja: '🇯🇵',
    ko: '🇰🇷', nl: '🇳🇱', sv: '🇸🇪', fi: '🇫🇮', no: '🇳🇴',
    unknown: '🌍',
};
const LANG_NAMES = {
    ru: 'Русский', en: 'Английский', uk: 'Украинский', kk: 'Казахский',
    be: 'Белорусский', de: 'Немецкий', fr: 'Французский', es: 'Испанский',
    it: 'Итальянский', tr: 'Турецкий', pt: 'Португальский', pl: 'Польский',
    ar: 'Арабский', zh: 'Китайский', ja: 'Японский', ko: 'Корейский',
    nl: 'Нидерландский', sv: 'Шведский', fi: 'Финский', no: 'Норвежский',
    unknown: 'Другие',
};

// ── Загрузка Chart.js ─────────────────────────────────────────────────────
async function ensureChartJs() {
    if (window.Chart) return;
    await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

// ── OVERVIEW: рендер ──────────────────────────────────────────────────────
async function renderOverview() {
    const main = document.getElementById('main-content');
    if (!main) return;
    main.innerHTML = statsOverviewTemplate();

    try {
        const resp = await fetch('/api/stats/overview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: getInitData() }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason);
        _overviewData = data;

        // KPI
        const ov = data.overview;
        document.getElementById('kpi-total-entries').textContent = fmt(ov.total_unique_participants);
        document.getElementById('kpi-active').textContent        = fmt(ov.active_giveaways);
        document.getElementById('kpi-total-gw').textContent      = fmt(ov.total_giveaways);
        document.getElementById('kpi-finished').textContent      = fmt(ov.finished_giveaways);

        // График трендов
        await ensureChartJs();
        renderTrendChart(data.trends);

        // Список розыгрышей (загружаем отдельно)
        await renderGiveawaysList();

    } catch (e) {
        console.error('[STATS overview]', e);
        const list = document.getElementById('stats-giveaway-list');
        if (list) list.innerHTML = `<div class="stats-empty"><div class="stats-empty-icon">😕</div><div class="stats-empty-text">Ошибка загрузки</div></div>`;
    }
}

function renderTrendChart(trends) {
    const canvas = document.getElementById('stats-overview-chart');
    if (!canvas || !window.Chart) return;
    destroyChart('overview');

    const labels = trends.map(t => {
        const d = new Date(t.day);
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
    });
    const values = trends.map(t => Number(t.new_entries) || 0);

    const isDark = document.documentElement.classList.contains('theme-dark')
                || !document.documentElement.classList.contains('theme-light');
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    const textColor = isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)';

    _chartInstances['overview'] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: values,
                borderColor: '#007AFF',
                backgroundColor: 'rgba(0,122,255,0.12)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: {
                callbacks: { label: ctx => ' ' + fmt(ctx.raw) + ' участников' }
            }},
            scales: {
                x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 6 } },
                y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 }, callback: v => fmt(v) }, beginAtZero: true }
            }
        }
    });
}

async function renderGiveawaysList() {
    const listEl = document.getElementById('stats-giveaway-list');
    if (!listEl) return;

    try {
        const resp = await fetch('/api/stats/giveaways_list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: getInitData() }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason);

        if (!data.items.length) {
            listEl.innerHTML = `<div class="stats-empty"><div class="stats-empty-icon">📊</div><div class="stats-empty-text">Нет розыгрышей</div></div>`;
            return;
        }

        listEl.innerHTML = data.items.map((g, i) => {
            const s = g.status || 'draft';
            const statusLabel = { active: 'Активен', finished: 'Завершён', draft: 'Черновик' };
            const channels = (g.channels || []).filter(Boolean).join(', ') || '—';
            return `
                <div class="stats-giveaway-item stats-giveaway-item--${s === 'active' ? 'active-giveaway' : ''}"
                     data-giveaway-id="${g.id}"
                     role="button" tabindex="0"
                     style="animation-delay:${i * 0.05}s">
                    <div class="stats-giveaway-avatar">🎁</div>
                    <div class="stats-giveaway-info">
                        <div class="stats-giveaway-title">${_esc(g.internal_title)}</div>
                        <div class="stats-giveaway-meta">${_esc(channels)}</div>
                        <span class="stats-giveaway-status-badge stats-giveaway-status-badge--${s}">
                            ${statusLabel[s] || s}
                        </span>
                    </div>
                    <div class="stats-giveaway-stat">
                        <div class="stats-giveaway-stat-num">${fmt(g.participants)}</div>
                        <div class="stats-giveaway-stat-label">участников</div>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="margin-top:4px;opacity:0.3">
                            <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                        </svg>
                    </div>
                </div>
            `;
        }).join('');

        // Клики по розыгрышам
        listEl.querySelectorAll('.stats-giveaway-item').forEach(item => {
            item.addEventListener('click', () => {
                const gid = item.dataset.giveawayId;
                const giveaway = data.items.find(g => String(g.id) === String(gid));
                if (giveaway) renderDetail(giveaway);
            });
        });

    } catch (e) {
        console.error('[STATS giveaways_list]', e);
        listEl.innerHTML = `<div class="stats-empty"><div class="stats-empty-icon">😕</div><div class="stats-empty-text">Ошибка загрузки</div></div>`;
    }
}

// ── DETAIL: рендер ────────────────────────────────────────────────────────
async function renderDetail(giveaway) {
    _currentView = 'detail';
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = statsDetailTemplate(giveaway);
    showBackButton(() => {
        hideBackButton();
        _currentView = 'overview';
        renderOverview();
    });

    try {
        await ensureChartJs();
        const resp = await fetch('/api/stats/giveaway', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: getInitData(), giveaway_id: giveaway.id }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.reason);
        _detailData = data;

        renderDetailMetrics(data);
        renderDetailChart(data, 'hourly');
        renderDetailFunnel(data);
        renderDetailSources(data);
        renderDetailNewSubs(data);
        renderDetailAudience(data);
        renderDetailLanguages(data);
        renderDetailFinance(data);
        renderDetailWinners(data);

        // Переключение графика
        document.querySelectorAll('.stats-chart-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.stats-chart-tab').forEach(t => t.classList.remove('stats-chart-tab--active'));
                tab.classList.add('stats-chart-tab--active');
                const period = tab.dataset.period;
                const titleEl = document.getElementById('detail-chart-title');
                if (titleEl) titleEl.textContent = period === 'hourly' ? 'По часам (7 дней)' : 'По дням (всё время)';
                renderDetailChart(_detailData, period);
            });
        });

    } catch (e) {
        console.error('[STATS detail]', e);
    }
}

function renderDetailMetrics(data) {
    const m = data.metrics;
    if (!m) return;
    const participants = Number(m.participants) || 0;
    const clicks       = Number(m.total_clicks) || 0;
    document.getElementById('dm-participants').textContent = fmt(participants);
    document.getElementById('dm-clicks').textContent       = fmt(clicks);
    document.getElementById('dm-conversion').textContent   = pct(participants, clicks);
}

function renderDetailChart(data, period) {
    const canvas = document.getElementById('stats-detail-chart');
    if (!canvas || !window.Chart) return;
    destroyChart('detail');

    const rows = period === 'hourly' ? data.hourly : data.daily;
    if (!rows || !rows.length) return;

    const isDark = document.documentElement.classList.contains('theme-dark')
                || !document.documentElement.classList.contains('theme-light');
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    const textColor = isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)';

    const labels = rows.map(r => {
        const d = new Date(r.bucket);
        return period === 'hourly'
            ? d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
            : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
    });
    const values = rows.map(r => Number(r.participants) || 0);

    // Накопительный (running total)
    const cumulative = values.reduce((acc, v, i) => {
        acc.push((acc[i - 1] || 0) + v);
        return acc;
    }, []);

    _chartInstances['detail'] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: cumulative,
                borderColor: '#007AFF',
                backgroundColor: 'rgba(0,122,255,0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: {
                callbacks: { label: ctx => ' ' + fmt(ctx.raw) + ' участников' }
            }},
            scales: {
                x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 6 } },
                y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 }, callback: v => fmt(v) }, beginAtZero: true }
            }
        }
    });
}

function renderDetailFunnel(data) {
    const el = document.getElementById('stats-funnel');
    if (!el) return;
    const f = data.funnel;
    if (!f) { el.innerHTML = '<div class="stats-empty-text">Нет данных</div>'; return; }

    const clicks    = Number(f.total_clicks)  || 0;
    const checked   = Number(f.checked)       || 0;
    const gotTicket = Number(f.got_ticket)    || 0;
    const max = clicks || 1;

    const steps = [
        { label: 'Нажали «Участвовать»', value: clicks,    color: '#007AFF', pctOfMax: 100 },
        { label: 'Прошли проверку',       value: checked,   color: '#30B0C7', pctOfMax: Math.round(checked / max * 100) },
        { label: 'Получили билет',         value: gotTicket, color: '#34C759', pctOfMax: Math.round(gotTicket / max * 100) },
    ];

    el.innerHTML = steps.map(step => `
        <div class="stats-funnel-step">
            <div class="stats-funnel-bar-wrap">
                <div class="stats-funnel-bar" style="--funnel-color:${step.color}; width:${step.pctOfMax}%">
                    <span class="stats-funnel-bar-label">${step.label}</span>
                </div>
            </div>
            <div class="stats-funnel-pct">${fmt(step.value)}</div>
        </div>
    `).join('');
}

function renderDetailSources(data) {
    const el = document.getElementById('stats-sources-list');
    if (!el) return;
    const sources = data.sources || [];

    if (!sources.length) {
        el.innerHTML = '<div class="stats-empty-text" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Данные появятся по мере участия</div>';
        return;
    }

    const maxVal = Math.max(...sources.map(s => Number(s.participants) || 0), 1);
    el.innerHTML = sources.map(s => {
        const cnt = Number(s.participants) || 0;
        const barPct = Math.round(cnt / maxVal * 100);
        const name = s.title || (s.username ? '@' + s.username : 'Канал #' + s.channel_id);
        return `
            <div class="stats-source-item">
                <div class="stats-source-avatar">📢</div>
                <div class="stats-source-info">
                    <div class="stats-source-name">${_esc(name)}</div>
                    <div class="stats-source-bar-wrap">
                        <div class="stats-source-bar" style="width:${barPct}%"></div>
                    </div>
                </div>
                <div class="stats-source-count">${fmt(cnt)}</div>
            </div>
        `;
    }).join('');
}

function renderDetailNewSubs(data) {
    const el = document.getElementById('stats-newsubs-list');
    const section = document.getElementById('stats-newsubs-section');
    if (!el) return;
    const newSubs = data.new_subs || [];

    if (!newSubs.length) {
        el.innerHTML = '<div class="stats-empty-text" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Данные появятся после участия пользователей</div>';
        return;
    }

    const total = newSubs.reduce((s, r) => s + (Number(r.new_subscribers) || 0), 0);
    el.innerHTML = `
        <div style="font-size:24px;font-weight:800;color:var(--color-success);margin-bottom:12px">+${fmt(total)} <span style="font-size:13px;font-weight:500;color:var(--color-text-secondary)">новых подписчиков</span></div>
        ${newSubs.map(r => `
            <div class="stats-newsub-item">
                <div class="stats-newsub-icon">📢</div>
                <div class="stats-newsub-name">${_esc(r.title || 'Канал #' + r.channel_id)}</div>
                <div class="stats-newsub-count">+${fmt(r.new_subscribers)}</div>
            </div>
        `).join('')}
    `;
}

function renderDetailAudience(data) {
    const premium = data.premium;
    if (!premium) return;

    const premiumCount = Number(premium.premium_count) || 0;
    const regularCount = Number(premium.regular_count) || 0;
    const total = premiumCount + regularCount || 1;
    const premiumPct = Math.round(premiumCount / total * 100);

    // Premium donut
    const donutPremiumCanvas = document.getElementById('donut-premium');
    if (donutPremiumCanvas && window.Chart) {
        destroyChart('donut-premium');
        _chartInstances['donut-premium'] = new Chart(donutPremiumCanvas, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [premiumCount, regularCount],
                    backgroundColor: ['#FFD700', 'rgba(255,255,255,0.1)'],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: false,
                cutout: '70%',
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
            }
        });
        document.getElementById('donut-premium-pct').textContent = premiumPct + '%';
        document.getElementById('donut-premium-legend').innerHTML = `
            <div class="stats-donut-legend-item"><div class="stats-donut-legend-dot" style="background:#FFD700"></div>Premium ${fmt(premiumCount)}</div>
            <div class="stats-donut-legend-item"><div class="stats-donut-legend-dot" style="background:rgba(255,255,255,0.2)"></div>Обычные ${fmt(regularCount)}</div>
        `;
    }

    // Langs donut
    const langs = (data.languages || []).slice(0, 5);
    const langsCanvas = document.getElementById('donut-langs');
    if (langsCanvas && window.Chart && langs.length) {
        destroyChart('donut-langs');
        const COLORS = ['#007AFF','#34C759','#FF9500','#FF2D55','#AF52DE'];
        const topLang = langs[0]?.lang || 'unknown';
        const topPct  = langs[0] ? Math.round(Number(langs[0].cnt) / langs.reduce((s,l) => s + Number(l.cnt), 0) * 100) : 0;
        _chartInstances['donut-langs'] = new Chart(langsCanvas, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: langs.map(l => Number(l.cnt)),
                    backgroundColor: COLORS,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: false,
                cutout: '70%',
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
            }
        });
        document.getElementById('donut-langs-top').textContent = (LANG_FLAGS[topLang] || '🌍');
        document.getElementById('donut-langs-legend').innerHTML = langs.slice(0, 3).map((l, i) => `
            <div class="stats-donut-legend-item">
                <div class="stats-donut-legend-dot" style="background:${COLORS[i]}"></div>
                ${LANG_FLAGS[l.lang] || '🌍'} ${fmt(l.cnt)}
            </div>
        `).join('');
    }
}

function renderDetailLanguages(data) {
    const el = document.getElementById('stats-lang-list');
    if (!el) return;
    const langs = data.languages || [];
    if (!langs.length) {
        el.innerHTML = '<div class="stats-empty-text" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Нет данных о языках</div>';
        return;
    }
    const total = langs.reduce((s, l) => s + Number(l.cnt), 0) || 1;
    el.innerHTML = langs.map(l => {
        const p = Math.round(Number(l.cnt) / total * 100);
        const flag = LANG_FLAGS[l.lang] || '🌍';
        const name = LANG_NAMES[l.lang] || l.lang;
        return `
            <div class="stats-lang-item">
                <div class="stats-lang-flag">${flag}</div>
                <div class="stats-lang-name">${name}</div>
                <div class="stats-lang-bar-wrap">
                    <div class="stats-lang-bar" style="width:${p}%"></div>
                </div>
                <div class="stats-lang-pct">${p}%</div>
            </div>
        `;
    }).join('');
}

function renderDetailFinance(data) {
    const el = document.getElementById('stats-finance-section');
    const rowsEl = document.getElementById('stats-finance-rows');
    if (!el || !rowsEl) return;

    const finance = data.finance || [];
    const promo   = data.promo_finance;
    const topRub  = finance.find(r => r.service_type === 'top_placement');
    const totalRub    = Number(topRub?.total_rub || 0);
    const totalStars  = Number(promo?.total_stars || 0);

    if (!totalRub && !totalStars) {
        el.style.display = 'none';
        return;
    }

    const rows = [];
    if (totalRub) rows.push({ label: '🏆 Топ-розыгрыши', value: `${totalRub.toLocaleString('ru-RU')} ₽` });
    if (totalStars) rows.push({ label: '📣 Продвижение в боте', value: `${totalStars.toLocaleString('ru-RU')} ⭐` });

    const participants = Number(data.metrics?.participants) || 1;
    if (totalRub && participants > 1) {
        rows.push({ label: 'Стоимость участника', value: `${Math.round(totalRub / participants)} ₽` });
    }

    rowsEl.innerHTML = rows.map((r, i) => `
        <div class="stats-finance-row ${i === rows.length - 1 ? 'stats-finance-row--total' : ''}">
            <div class="stats-finance-label">${r.label}</div>
            <div class="stats-finance-value">${r.value}</div>
        </div>
    `).join('');
}

function renderDetailWinners(data) {
    const section = document.getElementById('stats-winners-section');
    const listEl  = document.getElementById('stats-winners-list');
    if (!section || !listEl) return;
    const winners = data.winners || [];
    if (!winners.length) return;

    section.style.display = '';
    listEl.innerHTML = winners.map(w => {
        const name = w.first_name || (w.username ? '@' + w.username : 'Пользователь #' + w.user_id);
        return `
            <div class="stats-winner-item">
                <div class="stats-winner-rank stats-winner-rank--${w.rank}">${w.rank}</div>
                <div class="stats-winner-name">${_esc(name)}</div>
                ${w.username ? `<div class="stats-winner-id">@${w.username}</div>` : ''}
            </div>
        `;
    }).join('');
}

// ── Back Button ───────────────────────────────────────────────────────────
function showBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.show(); tg.BackButton.onClick(onBack); } catch (e) {}
}
function hideBackButton() {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.hide(); tg.BackButton.offClick(); } catch (e) {}
}

// ── Вспомогательная ───────────────────────────────────────────────────────
function _esc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Точка входа ───────────────────────────────────────────────────────────
function renderStatsPage() {
    _currentView = 'overview';
    // Уничтожаем все графики при переходе на страницу
    Object.keys(_chartInstances).forEach(destroyChart);
    renderOverview();
}

export { renderStatsPage };
