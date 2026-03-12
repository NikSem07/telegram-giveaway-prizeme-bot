// webapp/pages/creator/services/task-services-preview.template.js

const STEPS = [
    'Создавайте задания или пулл со множеством заданий со своими условиями (подписка на канал, просмотр ролика на YouTube и прочее)',
    'Устанавливайте размер вознаграждения за выполнение задания — сколько дополнительных билетов получит участник',
    'Подключайте задание к конкретному активному розыгрышу',
    'Все участники розыгрыша смогут увидеть задания и выполнить их в разделе «Задания» в режиме «Участник»',
    'Стоимость 1 задания: 199 ₽ / 199 ⭐️',
];

export default function taskServicesPreviewTemplate() {
    const steps = STEPS.map((text, i) => `
        <div class="tsp-step">
            <div class="tsp-step-num">${i + 1}</div>
            <p class="tsp-step-text">${text}</p>
        </div>
    `).join('');

    return `
        <div class="tsp-screen">

            <!-- Герой -->
            <div class="tsp-hero">
                <div class="tsp-hero-icon">✅</div>
                <h1 class="tsp-hero-title">Задания для участников</h1>
                <p class="tsp-hero-subtitle">
                    Создайте задания для участников розыгрыша, за выполнение они получат дополнительные билеты
                </p>
            </div>

            <!-- Блок инструкции -->
            <p class="tsp-section-title">Как это работает</p>
            <div class="tsp-steps-card">
                <div class="tsp-steps">
                    ${steps}
                </div>
            </div>

            <!-- Pop-up: нет активных розыгрышей -->
            <div class="tsp-popup-overlay" id="tsp-no-giveaway-overlay">
                <div class="tsp-popup-sheet" id="tsp-no-giveaway-sheet">
                    <div class="tsp-popup-icon">⚠️</div>
                    <p class="tsp-popup-title">Нет активных розыгрышей</p>
                    <p class="tsp-popup-text">Чтобы создать задания, сначала запустите хотя бы один розыгрыш</p>
                    <button type="button" class="tsp-popup-btn" id="tsp-no-giveaway-close">Понятно</button>
                </div>
            </div>

            <!-- Отступ под фиксированную кнопку -->
            <div class="tsp-bottom-spacer"></div>

        </div>

        <!-- Фиксированная кнопка -->
        <div class="tsp-footer">
            <button class="tsp-continue-btn" id="tsp-continue-btn" type="button">
                Продолжить
            </button>
        </div>
    `;
}
