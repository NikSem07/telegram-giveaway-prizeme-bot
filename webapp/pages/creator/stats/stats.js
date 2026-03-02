// webapp/pages/creator/stats/stats.js
import { statsOverviewTemplate, statsDetailTemplate } from './stats.template.js';

// ── Состояние ─────────────────────────────────────────────────────────────
let _allGiveaways = [];
let _detailData   = null;
let _charts       = {};

// ── Утилиты ───────────────────────────────────────────────────────────────
function getInitData() {
    return window.Telegram?.WebApp?.initData
        || sessionStorage.getItem('prizeme_init_data') || '';
}

function fmt(n) {
    const num = Number(n);
    if (!isFinite(num) || n === null || n === undefined || n === '') return '—';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 10000)   return Math.round(num / 1000) + 'K';
    if (num >= 1000)    return (num / 1000).toFixed(1) + 'K';
    return num.toLocaleString('ru-RU');
}

function pct(a, b) {
    const na = Number(a), nb = Number(b);
    if (!nb) return '0%';
    return Math.round(na / nb * 100) + '%';
}

function _pluralTickets(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return 'Билетов';
    if (mod10 === 1) return 'Билет';
    if (mod10 >= 2 && mod10 <= 4) return 'Билета';
    return 'Билетов';
}

function _pluralGiveaways(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return 'Розыгрышей';
    if (mod10 === 1) return 'Розыгрыш';
    if (mod10 >= 2 && mod10 <= 4) return 'Розыгрыша';
    return 'Розыгрышей';
}

function _esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function destroyChart(key) {
    if (_charts[key]) {
        try { _charts[key].destroy(); } catch(e) {}
        delete _charts[key];
    }
}

// ── Chart.js lazy-load ────────────────────────────────────────────────────
async function ensureChartJs() {
    if (window.Chart) return;
    await new Promise((res, rej) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
        s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
    });
}

// ── Тема ──────────────────────────────────────────────────────────────────
function isDark() {
    return document.documentElement.classList.contains('theme-dark') ||
           !document.documentElement.classList.contains('theme-light');
}

function chartColors() {
    return {
        grid:  isDark() ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
        text:  isDark() ? 'rgba(255,255,255,0.4)'  : 'rgba(0,0,0,0.4)',
    };
}

// ── Флаги / названия языков ───────────────────────────────────────────────
const LANG_FLAG = {ru:'🇷🇺',en:'🇬🇧',uk:'🇺🇦',kk:'🇰🇿',be:'🇧🇾',de:'🇩🇪',fr:'🇫🇷',
    es:'🇪🇸',it:'🇮🇹',tr:'🇹🇷',pt:'🇵🇹',pl:'🇵🇱',ar:'🇸🇦',zh:'🇨🇳',
    ja:'🇯🇵',ko:'🇰🇷',nl:'🇳🇱',sv:'🇸🇪',unknown:'🌍'};
const LANG_NAME = {ru:'Русский',en:'Английский',uk:'Украинский',kk:'Казахский',
    be:'Белорусский',de:'Немецкий',fr:'Французский',es:'Испанский',
    it:'Итальянский',tr:'Турецкий',pt:'Португальский',pl:'Польский',
    ar:'Арабский',zh:'Китайский',ja:'Японский',ko:'Корейский',
    nl:'Нидерландский',sv:'Шведский',unknown:'Другие'};

// ══════════════════════════════════════════════════════════════════════════
// OVERVIEW
// ══════════════════════════════════════════════════════════════════════════
async function renderOverview() {
    const main = document.getElementById('main-content');
    if (!main) return;
    main.innerHTML = statsOverviewTemplate();

    // Навешиваем фильтры
    document.getElementById('st-filters')?.addEventListener('click', e => {
        const btn = e.target.closest('.st-filter-btn');
        if (!btn) return;
        document.querySelectorAll('.st-filter-btn').forEach(b => b.classList.remove('st-filter-btn--on'));
        btn.classList.add('st-filter-btn--on');
        renderGwList(btn.dataset.filter);
    });

    await Promise.all([loadOverviewData(), loadGiveaways()]);
    _initLottie();
}

function _initLottie() {
    const wrap = document.getElementById('st-lottie-wrap');
    if (!wrap) return;
    // Уничтожаем предыдущую анимацию если есть
    if (wrap._lottieAnim) {
        try { wrap._lottieAnim.destroy(); } catch(e) {}
        wrap._lottieAnim = null;
        wrap.innerHTML = '';
    }

    if (!window.lottie) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js';
        s.onload = () => _playLottie(wrap);
        document.head.appendChild(s);
    } else {
        _playLottie(wrap);
    }
}

function _playLottie(wrap) {
    fetch('/miniapp-static/assets/gif/Programming-Computer.json')
        .then(r => r.json())
        .then(animData => {
            const anim = window.lottie.loadAnimation({
                container: wrap,
                renderer: 'svg',
                loop: true,
                autoplay: true,
                animationData: animData
            });
            wrap._lottieAnim = anim;
        })
        .catch(e => { console.warn('[stats/lottie]', e); wrap.style.display = 'none'; });
}

async function loadOverviewData() {
    try {
        const r = await fetch('/api/stats/overview', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ init_data: getInitData() })
        });
        const d = await r.json();
        if (!d.ok) return;

        const ov = d.overview;
        const totalEntries = Number(ov.total_entries) || 0;
        const totalGiveaways = (Number(ov.active_giveaways)||0) + (Number(ov.finished_giveaways)||0);

        document.getElementById('kpi-participants').textContent = fmt(totalEntries);
        document.getElementById('kpi-total').textContent        = fmt(totalGiveaways);

        // Склонение меток
        const lblP = document.getElementById('kpi-participants-lbl');
        if (lblP) lblP.textContent = _pluralTickets(totalEntries);
        const lblT = document.getElementById('kpi-total-lbl');
        if (lblT) lblT.textContent = _pluralGiveaways(totalGiveaways);

        document.getElementById('kpi-active').textContent       = fmt(ov.active_giveaways);
        document.getElementById('kpi-finished').textContent     = fmt(ov.finished_giveaways);

        // chart removed
    } catch(e) { console.error('[stats/overview]', e); }
}

function renderOverviewChart(trends) {
    // Ждём пока canvas будет в DOM с реальными размерами
    requestAnimationFrame(() => {
        const canvas = document.getElementById('overview-chart');
        if (!canvas) return;
        destroyChart('overview');

        const c = chartColors();
        const labels = trends.map(t => {
            const d = new Date(t.day);
            return d.toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit'});
        });
        const vals = trends.map(t => Number(t.new_entries) || 0);

        _charts['overview'] = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: vals,
                    borderColor: '#007AFF',
                    backgroundColor: 'rgba(0,122,255,0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#007AFF',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 600, easing: 'easeOutQuart' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isDark() ? '#1c1c1e' : '#fff',
                        titleColor: isDark() ? '#fff' : '#000',
                        bodyColor:  isDark() ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)',
                        borderColor: isDark() ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
                        borderWidth: 1,
                        callbacks: { label: ctx => ' ' + fmt(ctx.raw) + ' уч.' }
                    }
                },
                scales: {
                    x: {
                        grid: { color: c.grid, drawBorder: false },
                        ticks: { color: c.text, font: { size: 10 }, maxTicksLimit: 7 }
                    },
                    y: {
                        grid: { color: c.grid, drawBorder: false },
                        ticks: { color: c.text, font: { size: 10 }, callback: v => fmt(v) },
                        beginAtZero: true
                    }
                }
            }
        });
    });
}

async function loadGiveaways() {
    try {
        const r = await fetch('/api/stats/giveaways_list', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ init_data: getInitData() })
        });
        const d = await r.json();
        if (!d.ok) throw new Error(d.reason);
        _allGiveaways = d.items || [];
        renderGwList('all');
    } catch(e) {
        console.error('[stats/giveaways_list]', e);
        const el = document.getElementById('st-gw-list');
        if (el) el.innerHTML = `<div class="st-empty"><div class="st-empty-icon">😕</div><div class="st-empty-txt">Не удалось загрузить</div></div>`;
    }
}

function renderGwList(filter) {
    const el = document.getElementById('st-gw-list');
    if (!el) return;

    const filtered = filter === 'all'
        ? _allGiveaways.filter(g => g.status !== 'draft')
        : _allGiveaways.filter(g => g.status === filter);

    if (!filtered.length) {
        el.innerHTML = `<div class="st-empty"><div class="st-empty-icon">📊</div><div class="st-empty-txt">${filter === 'all' ? 'Нет розыгрышей' : 'Нет розыгрышей в этой категории'}</div></div>`;
        return;
    }

    const STATUS_LABEL = { active:'Активен', finished:'Завершён', draft:'Черновик', cancelled:'Отменён' };
    const STATUS_CLS   = { active:'active', finished:'finished', draft:'draft', cancelled:'cancelled' };

    el.innerHTML = filtered.map((g, i) => {
        const s   = g.status || 'draft';
        const chs = (g.channels || []).filter(Boolean).join(', ') || '—';

        const badgeColors = {
            active:    'background:rgba(52,199,89,0.18);color:#34C759;border:1px solid rgba(52,199,89,0.35)',
            finished:  'background:rgba(255,59,48,0.18);color:#FF453A;border:1px solid rgba(255,59,48,0.35)',
            draft:     'background:rgba(255,149,0,0.18);color:#FF9F0A;border:1px solid rgba(255,149,0,0.35)',
            cancelled: 'background:rgba(255,59,48,0.15);color:#FF453A;border:1px solid rgba(255,59,48,0.3)',
        };
        const badgeStyle = badgeColors[s] || badgeColors.draft;
        const badgeText  = { active:'Активен', finished:'Завершён', draft:'Черновик', cancelled:'Отменён' }[s] || s;

        const avatarUrl = g.first_channel_chat_id
            ? `/api/chat_avatar/${g.first_channel_chat_id}`
            : null;

        const avatarHtml = avatarUrl
            ? `<img src="${avatarUrl}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%"
                onerror="this.parentElement.innerHTML='🎁'">`
            : '🎁';

        return `
        <div class="st-gw-card" data-gid="${g.id}" style="animation-delay:${Math.min(i,6)*0.05}s">
            <div class="st-gw-card__left">
                <div class="st-gw-card__avatar">${avatarHtml}</div>
                <div class="st-gw-card__participants">
                    <img src="/miniapp-static/assets/icons/profile-icon.svg" width="13" height="13" style="opacity:0.8;flex-shrink:0;filter:brightness(10)">
                    ${fmt(g.participants)}
                </div>
            </div>
            <div class="st-gw-card__body">
                <div class="st-gw-card__top">
                    <span class="st-gw-card__channels">${_esc(chs)}</span>
                    <span class="st-gw-card__badge" style="${badgeStyle}">${badgeText}</span>
                </div>
                <div class="st-gw-card__title">${_esc(g.internal_title)}</div>
            </div>
            <div class="st-gw-card__arrow">
                <svg width="9" height="14" viewBox="0 0 9 14" fill="none">
                    <path d="M1.5 1l6 6-6 6" stroke="#737375" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
        </div>`;
    }).join('');

    // Делегирование — один обработчик на весь список
    el.onclick = (e) => {
        const item = e.target.closest('.st-gw-card');
        if (!item) return;
        const gid = item.dataset.gid;
        const giveaway = _allGiveaways.find(g => String(g.id) === String(gid));
        if (giveaway) renderDetail(giveaway);
    };
}

// ══════════════════════════════════════════════════════════════════════════
// DETAIL
// ══════════════════════════════════════════════════════════════════════════
async function renderDetail(giveaway) {
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = statsDetailTemplate(giveaway);
    _showBack(() => { _hideBack(); renderOverview(); });

    try {
        await ensureChartJs();
        const r = await fetch('/api/stats/giveaway', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ init_data: getInitData(), giveaway_id: giveaway.id })
        });
        const d = await r.json();
        if (!d.ok) throw new Error(d.reason);
        _detailData = d;

        _renderMetrics(d);
        _renderDetailChart(d, 'hourly');
        _renderFunnel(d);
        _renderSources(d);
        _renderNewSubs(d);
        _renderAudience(d);
        _renderLangs(d);
        _renderFinance(d);
        _renderWinners(d);

        // Переключение периода графика
        document.getElementById('st-detail-page')?.querySelectorAll('.st-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.st-tab').forEach(t => t.classList.remove('st-tab--on'));
                tab.classList.add('st-tab--on');
                const p = tab.dataset.period;
                const ttl = document.getElementById('detail-chart-ttl');
                if (ttl) ttl.textContent = p === 'hourly' ? 'По часам (7 дней)' : 'По дням (всё время)';
                _renderDetailChart(_detailData, p);
            });
        });

    } catch(e) {
        console.error('[stats/detail]', e);
    }
}

function _renderMetrics(d) {
    const m = d.metrics || {};
    const parts  = Number(m.participants)  || 0;
    const clicks = Number(m.total_clicks)  || 0;
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    el('dm-parts',  fmt(parts));
    el('dm-clicks', fmt(clicks));
    el('dm-conv',   pct(parts, clicks));
}

function _renderDetailChart(d, period) {
    requestAnimationFrame(() => {
        const canvas = document.getElementById('detail-chart');
        if (!canvas || !window.Chart) return;
        destroyChart('detail');

        const rows = (period === 'hourly' ? d.hourly : d.daily) || [];
        if (!rows.length) return;

        const c = chartColors();
        const labels = rows.map(r => {
            const dt = new Date(r.bucket);
            return period === 'hourly'
                ? dt.toLocaleString('ru-RU', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'})
                : dt.toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit'});
        });

        // Накопительный итог
        const cumul = [];
        let acc = 0;
        rows.forEach(r => { acc += Number(r.participants) || 0; cumul.push(acc); });

        _charts['detail'] = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: cumul,
                    borderColor: '#007AFF',
                    backgroundColor: 'rgba(0,122,255,0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#007AFF',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 500, easing: 'easeOutQuart' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isDark() ? '#1c1c1e' : '#fff',
                        titleColor: isDark() ? '#fff' : '#000',
                        bodyColor:  isDark() ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)',
                        borderColor: isDark() ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
                        borderWidth: 1,
                        callbacks: { label: ctx => ' ' + fmt(ctx.raw) + ' участников' }
                    }
                },
                scales: {
                    x: {
                        grid: { color: c.grid, drawBorder: false },
                        ticks: { color: c.text, font: { size: 10 }, maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: c.grid, drawBorder: false },
                        ticks: { color: c.text, font: { size: 10 }, callback: v => fmt(v) },
                        beginAtZero: true
                    }
                }
            }
        });
    });
}

function _renderFunnel(d) {
    const el = document.getElementById('st-funnel');
    if (!el) return;
    const f = d.funnel || {};
    const clicks    = Number(f.total_clicks) || 0;
    const checked   = Number(f.checked) || 0;
    const got       = Number(f.got_ticket) || 0;
    const max       = clicks || 1;

    const steps = [
        { label: 'Нажали «Участвовать»', val: clicks, w: 100,                           color: '#007AFF' },
        { label: 'Прошли проверку',       val: checked, w: Math.round(checked/max*100),  color: '#34AADC' },
        { label: 'Получили билет',         val: got,    w: Math.round(got/max*100),       color: '#34C759' },
    ];

    el.innerHTML = steps.map(s => `
        <div class="st-funnel-row">
            <div class="st-funnel-track">
                <div class="st-funnel-fill" style="background:${s.color};width:${s.w}%">
                    <span>${_esc(s.label)}</span>
                </div>
            </div>
            <div class="st-funnel-num">${fmt(s.val)}</div>
        </div>
    `).join('');
}

function _renderSources(d) {
    const el = document.getElementById('st-sources');
    if (!el) return;
    const srcs = d.sources || [];

    if (!srcs.length) {
        el.innerHTML = '<div class="st-empty-txt" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Данные появятся по мере участия</div>';
        return;
    }

    const maxV = Math.max(...srcs.map(s => Number(s.participants)||0), 1);
    el.innerHTML = srcs.map(s => {
        const cnt  = Number(s.participants) || 0;
        const w    = Math.round(cnt / maxV * 100);
        const name = s.title || (s.username ? '@'+s.username : 'Канал');
        return `
        <div class="st-src-row">
            <div class="st-src-icon">📢</div>
            <div class="st-src-body">
                <div class="st-src-name">${_esc(name)}</div>
                <div class="st-src-track"><div class="st-src-bar" style="width:${w}%"></div></div>
            </div>
            <div class="st-src-cnt">${fmt(cnt)}</div>
        </div>`;
    }).join('');
}

function _renderNewSubs(d) {
    const el = document.getElementById('st-newsubs');
    if (!el) return;
    const ns = d.new_subs || [];

    if (!ns.length) {
        el.innerHTML = '<div class="st-empty-txt" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Данные появятся после участия пользователей</div>';
        return;
    }

    const total = ns.reduce((s, r) => s + (Number(r.new_subscribers)||0), 0);
    el.innerHTML = `
        <div class="st-newsub-total">+${fmt(total)} <span>новых подписчиков</span></div>
        ${ns.map(r => `
        <div class="st-newsub-row">
            <div class="st-newsub-icon">📢</div>
            <div class="st-newsub-name">${_esc(r.title||'Канал')}</div>
            <div class="st-newsub-cnt">+${fmt(r.new_subscribers)}</div>
        </div>`).join('')}`;
}

function _renderAudience(d) {
    if (!window.Chart) return;

    const p   = d.premium || {};
    const pc  = Number(p.premium_count) || 0;
    const rc  = Number(p.regular_count) || 0;
    const tot = pc + rc || 1;
    const ppct = Math.round(pc / tot * 100);

    // Premium donut
    requestAnimationFrame(() => {
        const cv = document.getElementById('donut-premium');
        if (!cv) return;
        destroyChart('donut-premium');
        _charts['donut-premium'] = new Chart(cv, {
            type: 'doughnut',
            data: { datasets: [{ data: [pc, rc], backgroundColor:['#FFD700', isDark()?'rgba(255,255,255,0.1)':'rgba(0,0,0,0.08)'], borderWidth:0 }] },
            options: { responsive:false, cutout:'70%', plugins:{ legend:{display:false}, tooltip:{enabled:false} }, animation:{duration:500} }
        });
        const vEl = document.getElementById('donut-premium-val');
        if (vEl) vEl.textContent = ppct + '%';
        const legEl = document.getElementById('donut-premium-leg');
        if (legEl) legEl.innerHTML = `
            <div class="st-donut-leg"><div class="st-donut-dot" style="background:#FFD700"></div>⭐ ${fmt(pc)}</div>
            <div class="st-donut-leg"><div class="st-donut-dot" style="background:rgba(255,255,255,0.25)"></div>Обычные ${fmt(rc)}</div>`;
    });

    // Langs donut
    const langs = (d.languages || []).slice(0, 5);
    if (!langs.length) return;
    const COLORS = ['#007AFF','#34C759','#FF9500','#FF2D55','#AF52DE'];
    const topLang = langs[0]?.lang || 'unknown';
    const totalL  = langs.reduce((s,l) => s+Number(l.cnt), 0) || 1;

    requestAnimationFrame(() => {
        const cv = document.getElementById('donut-langs');
        if (!cv) return;
        destroyChart('donut-langs');
        _charts['donut-langs'] = new Chart(cv, {
            type: 'doughnut',
            data: { datasets: [{ data: langs.map(l=>Number(l.cnt)), backgroundColor:COLORS, borderWidth:0 }] },
            options: { responsive:false, cutout:'70%', plugins:{ legend:{display:false}, tooltip:{enabled:false} }, animation:{duration:500} }
        });
        const vEl = document.getElementById('donut-langs-val');
        if (vEl) vEl.textContent = LANG_FLAG[topLang] || '🌍';
        const legEl = document.getElementById('donut-langs-leg');
        if (legEl) legEl.innerHTML = langs.slice(0,3).map((l,i) => `
            <div class="st-donut-leg">
                <div class="st-donut-dot" style="background:${COLORS[i]}"></div>
                ${LANG_FLAG[l.lang]||'🌍'} ${fmt(l.cnt)}
            </div>`).join('');
    });
}

function _renderLangs(d) {
    const el = document.getElementById('st-langs');
    if (!el) return;
    const langs = d.languages || [];

    if (!langs.length) {
        el.innerHTML = '<div class="st-empty-txt" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Нет данных о языках</div>';
        return;
    }

    const total = langs.reduce((s,l) => s+Number(l.cnt), 0) || 1;
    el.innerHTML = langs.map(l => {
        const p    = Math.round(Number(l.cnt)/total*100);
        const flag = LANG_FLAG[l.lang] || '🌍';
        const name = LANG_NAME[l.lang] || l.lang;
        return `
        <div class="st-lang-row">
            <div class="st-lang-flag">${flag}</div>
            <div class="st-lang-name">${_esc(name)}</div>
            <div class="st-lang-track"><div class="st-lang-bar" style="width:${p}%"></div></div>
            <div class="st-lang-pct">${p}%</div>
        </div>`;
    }).join('');
}

function _renderFinance(d) {
    const section = document.getElementById('finance-section');
    const el      = document.getElementById('st-fin');
    if (!section || !el) return;

    const fin   = d.finance || [];
    const promo = d.promo_finance || {};
    const topRow   = fin.find(r => r.service_type === 'top_placement');
    const totalRub  = Number(topRow?.total_rub || 0);
    const totalStars = Number(promo.total_stars || 0);

    if (!totalRub && !totalStars) { section.style.display = 'none'; return; }
    section.style.display = '';

    const parts = Number(d.metrics?.participants) || 1;
    const rows = [];
    if (totalRub)   rows.push({ lbl: '🏆 Топ-розыгрыши', val: totalRub.toLocaleString('ru-RU') + ' ₽' });
    if (totalStars) rows.push({ lbl: '📣 Продвижение в боте', val: totalStars.toLocaleString('ru-RU') + ' ⭐' });
    if (totalRub && parts > 1) rows.push({ lbl: 'Стоимость участника', val: Math.round(totalRub/parts) + ' ₽', total: true });

    el.innerHTML = rows.map((r, i) => `
        <div class="st-fin-row ${r.total ? 'st-fin-row--total' : ''}">
            <div class="st-fin-lbl">${r.lbl}</div>
            <div class="st-fin-val">${r.val}</div>
        </div>`).join('');
}

function _renderWinners(d) {
    const section = document.getElementById('winners-section');
    const el      = document.getElementById('st-wins');
    if (!section || !el) return;
    const winners = d.winners || [];
    if (!winners.length) { section.style.display = 'none'; return; }
    section.style.display = '';

    el.innerHTML = winners.map(w => {
        const name = w.first_name || (w.username ? '@'+w.username : 'ID ' + w.user_id);
        return `
        <div class="st-win-row">
            <div class="st-win-rank st-win-rank--${w.rank}">${w.rank}</div>
            <div class="st-win-name">${_esc(name)}</div>
            ${w.username ? `<div class="st-win-id">@${w.username}</div>` : ''}
        </div>`;
    }).join('');
}

// ── Telegram Back Button ──────────────────────────────────────────────────
let _backCb = null;

function _showBack(cb) {
    _backCb = cb;
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.show(); tg.BackButton.onClick(_backCb); } catch(e) {}
}

function _hideBack() {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.hide(); if (_backCb) tg.BackButton.offClick(_backCb); _backCb = null; } catch(e) {}
}

// ── Точка входа ───────────────────────────────────────────────────────────
function renderStatsPage() {
    // Уничтожаем все старые графики
    Object.keys(_charts).forEach(destroyChart);
    _allGiveaways = [];
    _detailData   = null;
    renderOverview();
}

export { renderStatsPage };
