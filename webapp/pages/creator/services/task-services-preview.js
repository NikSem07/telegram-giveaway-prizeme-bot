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
export function renderTaskServicesPreviewPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Скрываем шапку и навбар
    _setShellVisibility(false);

    window.scrollTo({ top: 0, behavior: 'auto' });

    main.innerHTML = taskServicesPreviewTemplate();

    // BackButton → возврат в Сервисы
    const handleBack = () => {
        _hideBackButton(handleBack);
        _setShellVisibility(true);
        Router.navigate('services');
    };
    _showBackButton(handleBack);

    // Кнопка «Продолжить» → переход к форме создания заданий
    document.getElementById('tsp-continue-btn')
        ?.addEventListener('click', () => {
            _hideBackButton(handleBack);
            Router.navigate('task_services');
        });
}
