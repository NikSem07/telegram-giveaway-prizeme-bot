// webapp/pages/participant/tasks/tasks.template.js

export function tasksListTemplate() {
    return `
        <div class="pt-page" id="pt-screen-list">
            <div class="pt-header">
                <h2 class="pt-title">Задания</h2>
                <p class="pt-subtitle">Выполняйте задания и получайте дополнительные билеты</p>
            </div>
            <div class="pt-giveaway-list" id="pt-giveaway-list">
                <div class="pt-loading">Загрузка...</div>
            </div>
        </div>
    `;
}

export function taskDetailTemplate({ giveawayTitle, tasks, completedIds }) {
    const total     = tasks.length;
    const completed = tasks.filter(t => completedIds.has(t.id)).length;
    const allDone   = completed === total && total > 0;

    const typeIcon = (type) => {
        switch (type) {
            case 'telegram_subscribe':
            case 'telegram_comment':
            case 'telegram_post':
                return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M21.4 2.6L1.6 10.2c-.8.3-.8 1.4 0 1.7l4.8 1.6 1.8 5.7c.2.7 1.1.9 1.6.4l2.7-2.7 5.2 3.8c.6.4 1.4.1 1.6-.6l3.2-16.2c.2-1-.7-1.7-1.6-1.3z"
                          fill="currentColor"/>
                </svg>`;
            case 'external_video':
                return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58A2.78 2.78 0 0 0 3.41 19.6C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.95A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z"
                          fill="currentColor"/>
                    <polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02" fill="white"/>
                </svg>`;
            case 'external_subscribe':
            case 'external_post':
                return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"
                          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"
                          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>`;
            default:
                return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2"
                          stroke-linecap="round"/>
                </svg>`;
        }
    };

    const tasksHtml = tasks.map(task => {
        const done = completedIds.has(task.id);
        return `
            <div class="pt-task-card ${done ? 'pt-task-card--done' : ''}" data-task-id="${task.id}">
                <div class="pt-task-icon ${done ? 'pt-task-icon--done' : ''}">
                    ${done
                        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                               <path d="M20 6L9 17l-5-5" stroke="white" stroke-width="2.5"
                                     stroke-linecap="round" stroke-linejoin="round"/>
                           </svg>`
                        : typeIcon(task.type)
                    }
                </div>
                <div class="pt-task-body">
                    <div class="pt-task-title">${task.title}</div>
                    ${task.reward_tickets > 1
                        ? `<div class="pt-task-reward">+${task.reward_tickets} билета</div>`
                        : `<div class="pt-task-reward">+${task.reward_tickets} билет</div>`
                    }
                </div>
                <div class="pt-task-action">
                    ${done
                        ? `<div class="pt-task-done-badge">Выполнено</div>`
                        : `<button class="pt-task-btn" type="button"
                                   data-task-id="${task.id}"
                                   data-task-link="${task.link || ''}"
                                   data-secret="${task.secret_enabled ? '1' : '0'}">
                               Начать
                           </button>`
                    }
                </div>
            </div>
            ${task.secret_enabled && !done ? `
            <div class="pt-secret-block pt-secret-block--hidden" id="pt-secret-${task.id}">
                <input class="pt-secret-input" type="text"
                       placeholder="Введите секретный код"
                       id="pt-secret-input-${task.id}"
                       enterkeyhint="done" autocomplete="off" />
                <button class="pt-secret-submit" type="button" data-task-id="${task.id}">
                    Подтвердить
                </button>
            </div>
            ` : ''}
        `;
    }).join('');

    const totalReward = tasks
        .filter(t => !completedIds.has(t.id))
        .reduce((sum, t) => sum + (t.reward_tickets || 1), 0);

    return `
        <div class="pt-page" id="pt-screen-detail">
            <!-- Прогресс -->
            <div class="pt-progress-block">
                <div class="pt-progress-header">
                    <span class="pt-progress-label">Прогресс</span>
                    <span class="pt-progress-count" id="pt-progress-count">${completed}/${total}</span>
                </div>
                <div class="pt-progress-bar">
                    <div class="pt-progress-fill" id="pt-progress-fill"
                         style="width: ${total > 0 ? Math.round(completed / total * 100) : 0}%"></div>
                </div>
            </div>

            <!-- Список заданий -->
            <div class="pt-section-label">Задания</div>
            <div class="pt-task-list" id="pt-task-list">
                ${tasksHtml}
            </div>

            <!-- Кнопка получить награду -->
            <div class="pt-claim-wrap" id="pt-claim-wrap">
                <button class="pt-claim-btn ${allDone ? '' : 'pt-claim-btn--inactive'}"
                        id="pt-claim-btn" type="button" ${allDone ? '' : 'disabled'}>
                    ${allDone
                        ? '🎉 Забрать награду'
                        : `Выполните все задания (осталось ${total - completed})`
                    }
                </button>
            </div>
        </div>
    `;
}
