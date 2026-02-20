// webapp/pages/participant/tasks/tasks.template.js
export default function tasksTemplate(context = {}) {
    return `
        <div class="wip-screen">
            <div class="wip-animation" id="wip-anim-tasks"></div>
            <h2 class="wip-title">В разработке</h2>
            <p class="wip-subtitle">Скоро можно будет получать множество призов, выполняя различные задачи</p>
        </div>
    `;
}