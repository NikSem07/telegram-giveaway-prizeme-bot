// webapp/pages/creator/services/task-services-preview.js
import taskServicesPreviewTemplate from './task-services-preview.template.js';
import Router from '../../../shared/router.js';

// ── Основной рендер ───────────────────────────────────────────────────────
export function renderTaskServicesPreviewPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    // Скролл в начало
    window.scrollTo({ top: 0, behavior: 'auto' });

    main.innerHTML = taskServicesPreviewTemplate();

    // Кнопка «Продолжить» → переход к форме создания заданий
    document.getElementById('tsp-continue-btn')
        ?.addEventListener('click', () => {
            Router.navigate('task_services');
        });
}
