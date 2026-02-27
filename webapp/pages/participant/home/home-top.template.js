// webapp/pages/participant/home/home-top.template.js

export default function homeTopTemplate() {
    return `
        <!-- Герой-блок (тот же что на главной, но с ? вместо стрелки) -->
        <div class="ht-hero">
            <img
                class="ht-hero-img"
                src="/miniapp-static/assets/images/top-gift.webp"
                alt="Топ розыгрыши"
                draggable="false"
            />
            <div class="ht-hero-glass">
                <div class="ht-hero-text">
                    <span class="ht-label">РЕКОМЕНДУЕМ</span>
                    <span class="ht-title">🔥 Топ розыгрыши</span>
                </div>
                <button class="ht-info-btn" type="button" aria-label="Информация" disabled>
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                        <circle cx="9" cy="9" r="8" stroke="white" stroke-width="1.6" opacity="0.9"/>
                        <path d="M9 8v5" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
                        <circle cx="9" cy="5.5" r="1" fill="white"/>
                    </svg>
                </button>
            </div>
        </div>

        <!-- Список розыгрышей -->
        <div class="ht-list" id="ht-list">
            <div class="ht-loading">
                <div class="loading-dots">
                    <span class="loading-dot"></span>
                    <span class="loading-dot"></span>
                    <span class="loading-dot"></span>
                    <span class="loading-dot"></span>
                </div>
            </div>
        </div>

        <!-- Отступ снизу -->
        <div style="height: 32px;"></div>
    `;
}
