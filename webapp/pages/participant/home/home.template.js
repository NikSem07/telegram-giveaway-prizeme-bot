// webapp/pages/participant/home/home.template.js
export default function homeTemplate(context = {}) {
    const { topGiveaways = [], latestGiveaways = [] } = context;
    
    return `
        <div class="top-frame">
            <!-- Верхняя часть: изображение-герой -->
            <div class="top-hero">
                <img
                    class="top-hero-img"
                    src="/miniapp-static/assets/images/top-gift.webp"
                    alt="Топ розыгрыши"
                    draggable="false"
                />
                <!-- Liquid-glass подложка поверх изображения -->
                <div class="top-hero-glass">
                    <div class="top-hero-text">
                        <span class="top-label">РЕКОМЕНДУЕМ</span>
                        <span class="top-title-text">🔥 Топ розыгрыши</span>
                    </div>
                    <button class="top-arrow" type="button" aria-label="Открыть топ">
                        <img
                            class="top-arrow-img"
                            src="/miniapp-static/assets/icons/arrow-icon.svg"
                            alt=""
                            aria-hidden="true"
                        />
                    </button>
                </div>
            </div>
            <!-- Нижняя часть: список розыгрышей -->
            <div id="top-giveaways-list" class="top-list"></div>
        </div>

        <div class="section-title section-title-row" style="margin-top:18px;">
            <span>Все текущие розыгрыши</span>
            <span class="section-title-arrow">&gt;</span>
        </div>
        <div id="all-giveaways-list" style="margin-top:8px;"></div>
    `;
}
