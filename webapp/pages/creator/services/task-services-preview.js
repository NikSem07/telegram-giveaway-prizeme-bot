// webapp/pages/creator/services/task-services-preview.js
import taskServicesPreviewTemplate from './task-services-preview.template.js';
import Router from '../../../shared/router.js';

// ── Управление шапкой и навбаром ─────────────────────────────────────────
function _setShellVisibility(visible) {
    const topHeader = document.querySelector('.top-header');
    if (topHeader) topHeader.style.display = visible ? '' : 'none';
    if (visible) {
        document.body.classList.remove('page-checkout-services');
    } else {
        document.body.classList.add('page-checkout-services');
    }
}

// ── BackButton ────────────────────────────────────────────────────────────
function _showBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.show(); tg.BackButton.onClick(onBack); } catch (e) {}
}

function _hideBackButton(onBack) {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.BackButton.offClick(onBack); tg.BackButton.hide(); } catch (e) {}
}

// ── Основной рендер ───────────────────────────────────────────────────────
function _getInitData() {
    return window.Telegram?.WebApp?.initData
        || sessionStorage.getItem('prizeme_init_data') || '';
}

async function _hasActiveGiveaway() {
    try {
        const resp = await fetch('/api/creator_active_giveaways_count', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: _getInitData() }),
        });
        const data = await resp.json();
        return data.ok && data.count > 0;
    } catch (e) {
        console.error('[TSP] hasActiveGiveaway error:', e);
        // При ошибке сети — пускаем дальше, чтобы не блокировать пользователя
        return true;
    }
}

function _openNoGiveawayPopup() {
    const overlay = document.getElementById('tsp-no-giveaway-overlay');
    const sheet   = document.getElementById('tsp-no-giveaway-sheet');
    if (!overlay || !sheet) return;

    overlay.style.display = 'flex';
    requestAnimationFrame(() => {
        overlay.classList.add('tsp-popup-overlay--visible');
        sheet.classList.add('tsp-popup-sheet--visible');
    });
}

function _closeNoGiveawayPopup() {
    const overlay = document.getElementById('tsp-no-giveaway-overlay');
    const sheet   = document.getElementById('tsp-no-giveaway-sheet');
    if (!overlay || !sheet) return;

    overlay.classList.remove('tsp-popup-overlay--visible');
    sheet.classList.remove('tsp-popup-sheet--visible');
    sheet.addEventListener('transitionend', () => {
        overlay.style.display = 'none';
    }, { once: true });
}

export function renderTaskServicesPreviewPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    _setShellVisibility(false);
    window.scrollTo({ top: 0, behavior: 'auto' });

    main.innerHTML = taskServicesPreviewTemplate();

    const handleBack = () => {
        _hideBackButton(handleBack);
        _setShellVisibility(true);
        Router.navigate('services');
    };
    _showBackButton(handleBack);

    // Кнопка «Продолжить»
    document.getElementById('tsp-continue-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('tsp-continue-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Проверяем...'; }

        const hasActive = await _hasActiveGiveaway();

        if (btn) { btn.disabled = false; btn.textContent = 'Продолжить'; }

        if (!hasActive) {
            _openNoGiveawayPopup();
            return;
        }

        _hideBackButton(handleBack);
        Router.navigate('task_services');
    });

    // Закрытие pop-up
    document.getElementById('tsp-no-giveaway-close')?.addEventListener('click', _closeNoGiveawayPopup);
    document.getElementById('tsp-no-giveaway-overlay')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) _closeNoGiveawayPopup();
    });
}
