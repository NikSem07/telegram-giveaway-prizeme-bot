// webapp/pages/participant/home/home.template.js
export default function homeTemplate(context = {}) {
    const { topGiveaways = [], latestGiveaways = [] } = context;
    
    return `
        <div class="top-frame">
            <div class="top-label">Рекомендуем</div>

            <div class="top-title-row">
                <div class="top-title">
                    <span class="top-title-emoji">🔥</span>
                    <span class="top-title-text">Топ розыгрыши</span>
                </div>
                <button class="top-arrow" type="button" aria-label="Открыть топ">
                    <span class="top-arrow-icon">&gt;</span>
                </button>
            </div>

            <div id="top-giveaways-list" class="top-list"></div>
        </div>

        <div class="section-title section-title-row" style="margin-top:18px;">
            <span>Все текущие розыгрыши</span>
            <span class="section-title-arrow">&gt;</span>
        </div>
        <div id="all-giveaways-list" style="margin-top:8px;"></div>
    `;
}
