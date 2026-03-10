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

// ── Основной рендер ───────────────────────────────────────────────────────
export function renderTaskServicesPreviewPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Скрываем шапку и навбар
    _setShellVisibility(false);

    window.scrollTo({ top: 0, behavior: 'auto' });

    main.innerHTML = taskServicesPreviewTemplate();

    // Кнопка «Продолжить» → переход к форме создания заданий
    document.getElementById('tsp-continue-btn')
        ?.addEventListener('click', () => {
            Router.navigate('task_services');
        });
}
