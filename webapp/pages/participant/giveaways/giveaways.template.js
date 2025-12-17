// webapp/pages/participant/giveaways/giveaways.template.js
export default function giveawaysTemplate(context = {}) {
    const { user } = context;
    
    return `
        <div class="stub-card">
            <h2 class="stub-title">🎯 Мои розыгрыши</h2>
            <p class="stub-text">Здесь появятся ваши активные и прошедшие розыгрыши. Раздел находится в разработке.</p>
        </div>
    `;
}
