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

        <div class="catalog-header" style="margin-top:18px;">
            <span class="catalog-title">Каталог розыгрышей</span>
            <div class="catalog-filter" id="catalog-filter" aria-label="Сортировка">
                <span class="catalog-filter-label" id="catalog-filter-label">Сначала новые</span>
                <svg class="catalog-filter-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 4L6 8L10 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
        </div>
        <div id="all-giveaways-list" style="margin-top:4px;"></div>
    `;
}
