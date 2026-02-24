// webapp/pages/creator/services/services.js
import servicesTemplate from './services.template.js';
import TelegramData from '../../../shared/telegram-data.js';

// ====== Pop-up "В разработке" ======
function showWipModal() {
    document.getElementById('svc-wip-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'svc-wip-modal';
    modal.className = 'svc-wip-overlay';
    modal.innerHTML = `
        <div class="svc-wip-sheet">
            <p class="svc-wip-title">🚧 В разработке</p>
            <p class="svc-wip-text">Этот раздел скоро будет доступен. Следите за обновлениями!</p>
            <button class="svc-wip-btn" type="button" id="svc-wip-close">Понятно</button>
        </div>
    `;
    document.body.appendChild(modal);

    requestAnimationFrame(() => modal.classList.add('is-visible'));

    const close = () => {
        modal.classList.remove('is-visible');
        modal.addEventListener('transitionend', () => modal.remove(), { once: true });
    };

    document.getElementById('svc-wip-close').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
}

// ====== Инициализация выбора сервиса ======
function initServiceSelection() {
    const cards    = document.querySelectorAll('.svc-card');
    const footer   = document.getElementById('svc-footer');
    const continueBtn = document.getElementById('svc-continue-btn');

    let selectedId = null;

    cards.forEach(card => {
        card.addEventListener('click', () => {
            const id = card.dataset.serviceId;

            // Снимаем выделение с предыдущего
            if (selectedId && selectedId !== id) {
                document.querySelector(`[data-service-id="${selectedId}"]`)
                    ?.classList.remove('svc-card--active');
            }

            // Переключаем текущий
            const isAlreadySelected = card.classList.contains('svc-card--active');
            card.classList.toggle('svc-card--active', !isAlreadySelected);
            card.setAttribute('aria-pressed', String(!isAlreadySelected));

            selectedId = isAlreadySelected ? null : id;

            // Показываем / скрываем кнопку "Продолжить"
            const hasSelection = selectedId !== null;
            footer.classList.toggle('is-visible', hasSelection);
            footer.setAttribute('aria-hidden', String(!hasSelection));
        });
    });

    // Кнопка "Продолжить" — пока показываем заглушку
    continueBtn.addEventListener('click', showWipModal);
}

// ====== Основной рендер ======
function renderServicesPage() {
    const main = document.getElementById('main-content');
    if (!main) return;

    main.innerHTML = servicesTemplate({ user: TelegramData.getUserContext() });

    // Lottie-анимация
    if (window.lottie) {
        lottie.loadAnimation({
            container: document.getElementById('svc-hero-anim'),
            renderer:  'svg',
            loop:      true,
            autoplay:  true,
            path:      '/miniapp-static/assets/gif/Services-Main-Creator.json',
        });
    }

    initServiceSelection();
}

export { renderServicesPage };
