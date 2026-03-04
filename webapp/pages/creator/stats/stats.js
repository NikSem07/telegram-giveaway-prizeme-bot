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
    if (num >= 1000000) {
        const v = num / 1000000;
        return (v % 1 === 0 ? v.toFixed(0) : v.toFixed(2).replace(/\.?0+$/, '')) + 'м';
    }
    if (num >= 1000) {
        const v = num / 1000;
        return (v % 1 === 0 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, '')) + 'к';
    }
    return String(num);
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
    window.scrollTo({ top: 0, behavior: 'instant' });
    document.body.classList.add('page-stats');

    // Навешиваем фильтры
    document.getElementById('st-filters')?.addEventListener('click', e => {
        const btn = e.target.closest('.st-filter-btn');
        if (!btn) return;
        const scrollY = window.scrollY;
        document.querySelectorAll('.st-filter-btn').forEach(b => b.classList.remove('st-filter-btn--on'));
        btn.classList.add('st-filter-btn--on');
        renderGwList(btn.dataset.filter);
        requestAnimationFrame(() => window.scrollTo({ top: scrollY, behavior: 'instant' }));
    });

    await Promise.all([loadOverviewData(), loadGiveaways()]);
    _initLottie();
}

function _initLottie() {
    const wrap = document.getElementById('st-lottie-wrap');
    if (!wrap) return;
    if (wrap.dataset.loaded === '1') return; // уже запущена
    wrap.dataset.loaded = '1';

    const play = () => {
        if (wrap._lottieAnim) {
            try { wrap._lottieAnim.destroy(); } catch(e) {}
            wrap.innerHTML = '';
        }
        fetch('/miniapp-static/assets/gif/Programming-Computer.json')
            .then(r => r.json())
            .then(animData => {
                wrap._lottieAnim = window.lottie.loadAnimation({
                    container: wrap,
                    renderer: 'svg',
                    loop: true,
                    autoplay: true,
                    animationData: animData
                });
            })
            .catch(() => { wrap.style.display = 'none'; });
    };

    if (!window.lottie) {
        // Проверяем не грузится ли уже скрипт
        if (document.querySelector('script[data-lottie]')) {
            // Ждём загрузки
            document.querySelector('script[data-lottie]').addEventListener('load', play, { once: true });
            return;
        }
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js';
        s.dataset.lottie = '1';
        s.onload = play;
        document.head.appendChild(s);
    } else {
        play();
    }
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
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (giveaway.status === 'active' && giveaway.end_at_utc) {
        _startDetailTimer(giveaway.end_at_utc);
    }
    _showBack(() => {
        _hideBack();
        renderOverview().then(() => {
            window.scrollTo({ top: 0, behavior: 'instant' });
        });
    });

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
        _initCsvBtn(giveaway.id);
        _renderDetailChart(d, 'all', 'hourly');
        const totalEl = document.getElementById('detail-chart-total');
        if (totalEl) totalEl.textContent = (Number(d.metrics?.participants) || 0).toLocaleString('ru-RU');
        _renderFunnel(d);
        _renderSources(d);
        _renderNewSubs(d);
        _renderAudience(d);
        _renderLangs(d);
        _renderFinance(d);
        _renderWinners(d);

        // Переключение периода и группировки
        let _chartPeriod = 'all';
        let _chartGroup  = 'hourly';

        document.getElementById('chart-period-btns')?.addEventListener('click', e => {
            const btn = e.target.closest('.st-chart-btn');
            if (!btn) return;
            _chartPeriod = btn.dataset.period;
            document.querySelectorAll('#chart-period-btns .st-chart-btn').forEach(b => b.classList.remove('st-chart-btn--on'));
            btn.classList.add('st-chart-btn--on');
            _renderDetailChart(_detailData, _chartPeriod, _chartGroup);
        });

        document.getElementById('chart-group-btns')?.addEventListener('click', e => {
            const btn = e.target.closest('.st-chart-btn');
            if (!btn) return;
            _chartGroup = btn.dataset.group;
            document.querySelectorAll('#chart-group-btns .st-chart-btn').forEach(b => b.classList.remove('st-chart-btn--on'));
            btn.classList.add('st-chart-btn--on');
            _renderDetailChart(_detailData, _chartPeriod, _chartGroup);
        });

    } catch(e) {
        console.error('[stats/detail]', e);
    }
}

function _renderMetrics(d) {
    const m      = d.metrics || {};
    const parts  = Number(m.participants) || 0;
    const clicks = Number(m.total_clicks) || 0;
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

    el('dm-parts',  fmt(parts));
    el('dm-clicks', fmt(clicks));
    el('dm-conv',   pct(parts, clicks));

    const partsLbl  = document.getElementById('dm-parts-lbl');
    const clicksLbl = document.getElementById('dm-clicks-lbl');
    if (partsLbl)  partsLbl.textContent  = _pluralParticipants(parts).toUpperCase();
    if (clicksLbl) clicksLbl.textContent = _pluralClicks(clicks).toUpperCase();
}

function _initCsvBtn(giveawayId) {
    const btn      = document.getElementById('dm-csv-btn');
    const modal    = document.getElementById('st-csv-modal');
    if (!btn || !modal) return;

    // Переносим модал в body чтобы position:fixed работало от viewport
    if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }

    const backdrop = document.getElementById('st-csv-backdrop');
    const cancel   = document.getElementById('st-csv-cancel');
    const confirm  = document.getElementById('st-csv-confirm');
    const content  = document.getElementById('st-csv-content');

    const open = () => {
        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('st-csv-modal--open'));
    };

    const close = () => {
        modal.classList.remove('st-csv-modal--open');
        setTimeout(() => {
            modal.style.display = 'none';
            // Сбрасываем состояние контента
            if (content) {
                content.innerHTML = `
                    <div class="st-csv-title">Хотите выгрузить CSV файл?</div>
                    <div class="st-csv-desc">Бот вышлет CSV файл со статистикой, вы также сможете вернуться обратно в приложение</div>
                    <div class="st-csv-btns">
                        <button class="st-csv-btn st-csv-btn--cancel" id="st-csv-cancel">Отмена</button>
                        <button class="st-csv-btn st-csv-btn--confirm" id="st-csv-confirm">Да</button>
                    </div>`;
                // Перевешиваем обработчики после перерисовки
                document.getElementById('st-csv-cancel')?.addEventListener('click', close);
                document.getElementById('st-csv-confirm')?.addEventListener('click', handleConfirm);
            }
        }, 280);
    };

    const handleConfirm = async () => {
        // Показываем состояние загрузки
        if (content) {
            content.innerHTML = `
                <div class="st-csv-loading-txt">Подождите несколько секунд,<br>идёт выгрузка CSV‑файла…</div>`;
        }

        try {
            const r = await fetch('/api/stats/request_csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: getInitData(), giveaway_id: giveawayId })
            });
            const d = await r.json();
            close();
            if (d.ok) {
                // Открываем чат с ботом (бот уже отправил файл туда)
                const botUsername = d.bot_username || 'PrizeMeRaffleBot';
                window.Telegram?.WebApp?.openTelegramLink(`https://t.me/${botUsername}`);
            }
        } catch (e) {
            console.error('[csv] error:', e);
            close();
        }
    };

    btn.addEventListener('click', open);
    backdrop?.addEventListener('click', close);
    cancel?.addEventListener('click', close);
    confirm?.addEventListener('click', handleConfirm);
}

let _detailTimerInterval = null;

function _startDetailTimer(endedAt) {
    if (_detailTimerInterval) clearInterval(_detailTimerInterval);
    const endMs = new Date(endedAt).getTime();
    const update = () => {
        const el = document.getElementById('detail-timer');
        if (!el) { clearInterval(_detailTimerInterval); return; }
        const diff = endMs - Date.now();
        if (diff <= 0) { el.textContent = 'Завершён'; clearInterval(_detailTimerInterval); return; }
        const d = Math.floor(diff / 86400000);
        const h = Math.floor((diff % 86400000) / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        el.textContent = d > 0
            ? `${d} дн., ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
            : `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    };
    update();
    _detailTimerInterval = setInterval(update, 1000);
}

function _pluralParticipants(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return 'участников';
    if (mod10 === 1) return 'участвует';
    if (mod10 >= 2 && mod10 <= 4) return 'участвуют';
    return 'участвуют';
}

function _pluralClicks(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return 'кликов';
    if (mod10 === 1) return 'клик';
    if (mod10 >= 2 && mod10 <= 4) return 'клика';
    return 'кликов';
}

function _renderDetailChart(d, period = 'all', group = 'hourly') {
    requestAnimationFrame(() => {
        const canvas = document.getElementById('detail-chart');
        if (!canvas || !window.Chart) return;
        destroyChart('detail');

        const sourceRows = (group === 'hourly' ? d.hourly : d.daily) || [];
        if (!sourceRows.length) return;

        // Фильтр по периоду от конца розыгрыша (или NOW если активный)
        const giveaway  = d.giveaway || {};
        const endMs     = giveaway.end_at_utc ? new Date(giveaway.end_at_utc).getTime() : Date.now();
        const periodMs  = { 'all': null, '24h': 86400000, '7d': 7 * 86400000, '30d': 30 * 86400000 };
        const cutoffMs  = periodMs[period] != null ? endMs - periodMs[period] : null;

        const filtered = cutoffMs
            ? sourceRows.filter(r => new Date(r.bucket).getTime() >= cutoffMs)
            : sourceRows;

        if (!filtered.length) return;

        // Накопительный итог от начала отфильтрованного диапазона
        const cumul = [];
        let acc = 0;
        filtered.forEach(r => { acc += Number(r.participants) || 0; cumul.push(acc); });

        // Обновляем счётчик "Участвуют" над графиком
        const totalEl = document.getElementById('detail-chart-total');
        if (totalEl) totalEl.textContent = (Number(d.metrics?.participants) || 0).toLocaleString('ru-RU');

        // Форматирование меток оси X
        const labels = filtered.map(r => {
            const dt = new Date(r.bucket);
            return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
        });

        const maxVal  = Math.max(...cumul, 1);
        const rawStep = maxVal / 4;
        const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
        const stepSize  = Math.ceil(rawStep / magnitude) * magnitude || 1;

        const c = chartColors();

        _charts['detail'] = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: cumul,
                    borderColor: '#007AFF',
                    backgroundColor: 'rgba(0,122,255,0.08)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: '#007AFF',
                    pointHoverBorderColor: '#fff',
                    pointHoverBorderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 400, easing: 'easeOutQuart' },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isDark() ? '#2c2c2e' : '#fff',
                        titleColor: isDark() ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.5)',
                        bodyColor:  isDark() ? '#fff' : '#000',
                        borderColor: isDark() ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)',
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 10,
                        displayColors: false,
                        callbacks: {
                            title: items => items[0]?.label || '',
                            label: ctx => ctx.raw.toLocaleString('ru-RU') + ' участников',
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            color: c.text,
                            font: { size: 10 },
                            maxTicksLimit: 5,
                            maxRotation: 0,
                        }
                    },
                    y: {
                        grid: { color: c.grid },
                        border: { display: false },
                        beginAtZero: true,
                        ticks: {
                            color: c.text,
                            font: { size: 10 },
                            stepSize,
                            precision: 0,
                            callback: v => Number.isInteger(v) ? v.toLocaleString('ru-RU') : null,
                        }
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
    const got       = Number(f.got_ticket) || 0;
    const max       = clicks || 1;

    const steps = [
        { label: 'Нажали «Участвовать»', val: clicks, w: 100,                        color: '#007AFF' },
        { label: 'Получили билет',        val: got,    w: Math.round(got/max*100),    color: '#34C759' },
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

    const srcs    = d.sources || [];
    const total   = srcs.reduce((s, r) => s + (Number(r.participants) || 0), 0);
    const metrics = d.metrics || {};
    const totalParts = Number(metrics.participants) || 0;
    const otherCnt = Math.max(totalParts - total, 0);

    const rows = [...srcs];

    if (!rows.length && !otherCnt) {
        el.innerHTML = '<div class="st-empty-txt" style="padding:8px 0;font-size:13px;color:var(--color-text-secondary)">Данные появятся по мере участия</div>';
        return;
    }

    const maxV = Math.max(...rows.map(s => Number(s.participants) || 0), otherCnt, 1);

    const rowsHtml = rows.map(s => {
        const cnt  = Number(s.participants) || 0;
        const w    = Math.round(cnt / maxV * 100);
        const name = s.title || (s.username ? '@' + s.username : 'Канал');
        const chatId = s.chat_id || s.channel_id || null;
        const avatarHtml = chatId
            ? `<img src="/api/chat_avatar/${chatId}" alt=""
                style="width:100%;height:100%;object-fit:cover;border-radius:50%"
                onerror="this.parentElement.innerHTML='📢'">`
            : '📢';
        return `
        <div class="st-src-row">
            <div class="st-src-icon st-src-icon--round">${avatarHtml}</div>
            <div class="st-src-body">
                <div class="st-src-name">${_esc(name)}</div>
                <div class="st-src-track"><div class="st-src-bar" style="width:${w}%"></div></div>
            </div>
            <div class="st-src-cnt">${fmt(cnt)}</div>
        </div>`;
    });

    if (otherCnt > 0 || rows.length > 0) {
        const w = Math.round(otherCnt / maxV * 100);
        rowsHtml.push(`
        <div class="st-src-row">
            <div class="st-src-icon st-src-icon--round" style="background:rgba(255,255,255,0.06);font-size:16px;display:flex;align-items:center;justify-content:center">🌐</div>
            <div class="st-src-body">
                <div class="st-src-name">Другие источники</div>
                <div class="st-src-track"><div class="st-src-bar" style="width:${w}%;background:rgba(255,255,255,0.3)"></div></div>
            </div>
            <div class="st-src-cnt">${fmt(otherCnt)}</div>
        </div>`);
    }

    el.innerHTML = rowsHtml.join('');
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

    // Получаем список новых подписчиков с именами
    const newUsers = d.new_sub_users || [];

    el.innerHTML = `
        <div class="st-newsub-total">+${fmt(total)} <span>новых подписчиков</span></div>
        ${ns.map(r => {
            const avatarHtml = r.chat_id
                ? `<img src="/api/chat_avatar/${r.chat_id}" alt=""
                    style="width:100%;height:100%;object-fit:cover;border-radius:50%"
                    onerror="this.parentElement.innerHTML='📢'">`
                : '📢';
            return `
            <div class="st-newsub-row">
                <div class="st-src-icon st-src-icon--round">${avatarHtml}</div>
                <div class="st-newsub-name">${_esc(r.title || r.username || 'Канал')}</div>
                <div class="st-newsub-cnt">+${fmt(r.new_subscribers)}</div>
            </div>`;
        }).join('')}
        ${newUsers.length ? `
        <div class="st-newsub-users-lbl">Пользователи</div>
        ${newUsers.map(u => {
            const name = u.first_name || (u.username ? '@'+u.username : 'Участник');
            return `
            <div class="st-newsub-user-row">
                <div class="st-newsub-user-ava">
                    ${u.photo_url
                        ? `<img src="${_esc(u.photo_url)}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%">`
                        : name[0].toUpperCase()}
                </div>
                <div class="st-newsub-user-name">${_esc(name)}</div>
            </div>`;
        }).join('')}` : ''}`;
}

function _renderAudience(d) {
    const el = document.getElementById('st-aud-premium');
    if (!el) return;

    const p   = d.premium || {};
    const pc  = Number(p.premium_count) || 0;
    const rc  = Number(p.regular_count) || 0;
    const tot = pc + rc || 1;
    const ppct = Math.round(pc / tot * 100);
    const rpct = 100 - ppct;

    el.innerHTML = `
        <div class="st-aud-pie-wrap">
            <canvas id="donut-premium" width="140" height="140"></canvas>
            <div class="st-aud-pie-center">
                <div class="st-aud-pie-val">${ppct}%</div>
                <div class="st-aud-pie-sub">Premium</div>
            </div>
        </div>
        <div class="st-aud-legend">
            <div class="st-aud-leg-row">
                <div class="st-aud-leg-dot" style="background:#FFD700"></div>
                <div class="st-aud-leg-lbl">⭐ Premium</div>
                <div class="st-aud-leg-val">${fmt(pc)}</div>
                <div class="st-aud-leg-pct">${ppct}%</div>
            </div>
            <div class="st-aud-leg-row">
                <div class="st-aud-leg-dot" style="background:rgba(255,255,255,0.25)"></div>
                <div class="st-aud-leg-lbl">Standard</div>
                <div class="st-aud-leg-val">${fmt(rc)}</div>
                <div class="st-aud-leg-pct">${rpct}%</div>
            </div>
        </div>`;

    if (!window.Chart) return;
    requestAnimationFrame(() => {
        const cv = document.getElementById('donut-premium');
        if (!cv) return;
        destroyChart('donut-premium');
        _charts['donut-premium'] = new Chart(cv, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [pc || 0.001, rc || 0.001],
                    backgroundColor: ['#FFD700', isDark() ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: false,
                cutout: '68%',
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                animation: { duration: 600 }
            }
        });
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
        const name = w.username ? '@'+w.username : (w.first_name || 'ID ' + w.user_id);
        const ticket = w.ticket_code || '—';
        return `
        <div class="st-win-row">
            <div class="st-win-rank st-win-rank--${w.rank}">${w.rank}</div>
            <div class="st-win-name">${_esc(name)}</div>
            <div class="st-win-id">Билет: <b>${_esc(ticket)}</b></div>
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
    if (_detailTimerInterval) { clearInterval(_detailTimerInterval); _detailTimerInterval = null; }
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.hide(); if (_backCb) tg.BackButton.offClick(_backCb); _backCb = null; } catch(e) {}
}

// ── Точка входа ───────────────────────────────────────────────────────────
function renderStatsPage() {
    Object.keys(_charts).forEach(destroyChart);
    _allGiveaways = [];
    _detailData   = null;
    document.body.classList.add('page-stats');
    renderOverview();
}

export { renderStatsPage };
