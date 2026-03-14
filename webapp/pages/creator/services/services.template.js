// webapp/pages/creator/services/services.template.js

const SERVICES = [
  {
    id: "top_placement",
    emoji: "🏆",
    title: "Включение в топ-розыгрыши",
    description:
      "Розыгрыш будет опубликован в блоке «Топ-розыгрыши» на главной странице режима «Участник»",
  },
  {
    id: "bot_promotion",
    emoji: "📣",
    title: "Продвижение в боте",
    description:
      "Розыгрыш будет опубликован в боте и пользователи получат уведомление с возможностью принять участие",
  },
  {
    id: "tasks",
    emoji: "✅",
    title: "Задания для участников",
    description:
      "Создайте задания для участников розыгрыша, за выполнение они получат дополнительные билеты",
  },
];

export default function servicesTemplate(context = {}) {
  const serviceCards = SERVICES.map(
    (s) => `
        <div class="svc-card" data-service-id="${s.id}" role="button" tabindex="0" aria-pressed="false">
            <div class="svc-card-header">
                <span class="svc-card-emoji">${s.emoji}</span>
                <span class="svc-card-title">${s.title}</span>
            </div>
            <p class="svc-card-desc">${s.description}</p>
        </div>
    `,
  ).join("");

  return `
        <div class="svc-screen">

            <div class="svc-hero">
                <div class="svc-hero-anim" id="svc-hero-anim"></div>
                <h1 class="svc-hero-title">Сервисы для создателей</h1>
                <p class="svc-hero-subtitle">Выберите один из сервисов ниже для вовлечения своей аудитории</p>
            </div>

            <div class="svc-list">
                ${serviceCards}
            </div>

            <div class="svc-bottom-spacer"></div>
        </div>

        <!-- Кнопка «Продолжить» -->
        <div class="svc-footer" id="svc-footer" aria-hidden="true">
            <button class="svc-continue-btn" id="svc-continue-btn" type="button">
                Продолжить
            </button>
        </div>
    `;
}
