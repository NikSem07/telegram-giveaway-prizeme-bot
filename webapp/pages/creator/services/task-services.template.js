// webapp/pages/creator/services/task-services.template.js

export const TASK_TYPES = [
    // Telegram
    { id: 'telegram_subscribe', group: 'telegram', label: 'Подписка на канал',   hasLink: true,  hasSecret: false },
    { id: 'telegram_comment',   group: 'telegram', label: 'Комментарий под постом', hasLink: true, hasSecret: false },
    { id: 'telegram_post',      group: 'telegram', label: 'Просмотр поста',      hasLink: true,  hasSecret: false },
    // Внешние
    { id: 'external_video',     group: 'external', label: 'Просмотр видео',      hasLink: true,  hasSecret: true  },
    { id: 'external_post',      group: 'external', label: 'Пост в соцсетях',     hasLink: true,  hasSecret: true  },
    { id: 'external_subscribe', group: 'external', label: 'Подписка на соцсети', hasLink: true,  hasSecret: true  },
    // Кастомное
    { id: 'custom',             group: 'custom',   label: 'Своё задание',        hasLink: true,  hasSecret: true  },
];

export default function taskServicesTemplate() {
    return `
        <div class="ts-screen">

            <!-- ── Блок 1: Описание пулла ────────────────────────────── -->
            <div class="ts-section">
                <p class="ts-section-label">Описание блока заданий</p>
                <div class="ts-card">
                    <textarea
                        id="ts-description"
                        class="ts-textarea"
                        placeholder="Кратко опишите задания для участников..."
                        maxlength="150"
                        rows="3"
                        enterkeyhint="done"
                    ></textarea>
                    <div class="ts-char-counter">
                        <span id="ts-desc-count">0</span>/150
                    </div>
                </div>
            </div>

            <!-- ── Блок 2: Лимит выполнений ──────────────────────────── -->
            <div class="ts-section">
                <p class="ts-section-label">Лимит выполнений</p>
                <div class="ts-card ts-limit-card">
                    <div class="ts-limit-toggle">
                        <button type="button"
                                class="ts-limit-btn ts-limit-btn--active"
                                id="ts-limit-unlimited"
                                data-mode="unlimited">
                            Без ограничений
                        </button>
                        <button type="button"
                                class="ts-limit-btn"
                                id="ts-limit-custom"
                                data-mode="custom">
                            Указать число
                        </button>
                    </div>
                    <div class="ts-limit-input-wrap" id="ts-limit-input-wrap" style="display:none">
                        <input type="number" id="ts-limit-value" class="ts-input"
                               placeholder="Например: 100" min="1" max="999999"
                               enterkeyhint="done">
                    </div>
                </div>
            </div>

            <!-- ── Блок 3: Список заданий ─────────────────────────────── -->
            <div class="ts-section">
                <p class="ts-section-label">Задания</p>

                <!-- Свёрнутые задания -->
                <div class="ts-tasks-list" id="ts-tasks-list"></div>

                <!-- Форма нового задания (скрыта по умолчанию) -->
                <div class="ts-task-form" id="ts-task-form" style="display:none">
                    <div class="ts-card ts-task-form-card">

                        <!-- Группы типов -->
                        <div class="ts-type-groups" id="ts-type-groups">
                            <div class="ts-type-group">
                                <p class="ts-type-group-label">В Telegram</p>
                                <div class="ts-type-chips">
                                    <button type="button" class="ts-type-chip" data-type="telegram_subscribe">Подписка на канал</button>
                                    <button type="button" class="ts-type-chip" data-type="telegram_comment">Комментарий</button>
                                    <button type="button" class="ts-type-chip" data-type="telegram_post">Просмотр поста</button>
                                </div>
                            </div>
                            <div class="ts-type-group">
                                <p class="ts-type-group-label">На внешних ресурсах</p>
                                <div class="ts-type-chips">
                                    <button type="button" class="ts-type-chip" data-type="external_video">Просмотр видео</button>
                                    <button type="button" class="ts-type-chip" data-type="external_post">Пост в соцсетях</button>
                                    <button type="button" class="ts-type-chip" data-type="external_subscribe">Подписка на соцсети</button>
                                </div>
                            </div>
                            <div class="ts-type-group">
                                <p class="ts-type-group-label">Кастомное</p>
                                <div class="ts-type-chips">
                                    <button type="button" class="ts-type-chip" data-type="custom">Своё задание</button>
                                </div>
                            </div>
                        </div>

                        <!-- Название -->
                        <div class="ts-field" id="ts-field-title">
                            <label class="ts-field-label" for="ts-task-title">Название задания</label>
                            <input type="text" id="ts-task-title" class="ts-input"
                                   placeholder="Например: Подписаться на канал"
                                   maxlength="30" enterkeyhint="done">
                            <div class="ts-char-counter">
                                <span id="ts-title-count">0</span>/30
                            </div>
                        </div>

                        <!-- Ссылка -->
                        <div class="ts-field" id="ts-field-link">
                            <label class="ts-field-label" for="ts-task-link">Ссылка на задание</label>
                            <input type="url" id="ts-task-link" class="ts-input"
                                   placeholder="https://..." enterkeyhint="done">
                        </div>

                        <!-- Секретный код (только для external и custom) -->
                        <div class="ts-field ts-field--secret" id="ts-field-secret" style="display:none">
                            <button type="button" class="ts-secret-toggle" id="ts-secret-toggle">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                </svg>
                                <span id="ts-secret-toggle-label">Добавить секретный код</span>
                            </button>
                            <div class="ts-secret-input-wrap" id="ts-secret-input-wrap" style="display:none">
                                <input type="text" id="ts-task-secret" class="ts-input"
                                       placeholder="Например: ABC123"
                                       maxlength="10" enterkeyhint="done">
                                <p class="ts-hint">Код должен быть легко находим для участников — например, указан в ролике на YouTube.</p>
                            </div>
                        </div>

                        <!-- Награда -->
                        <div class="ts-field" id="ts-field-reward">
                            <label class="ts-field-label">Награда за выполнение</label>
                            <div class="ts-reward-row">
                                <button type="button" class="ts-reward-chip" data-reward="1">+1</button>
                                <button type="button" class="ts-reward-chip" data-reward="2">+2</button>
                                <button type="button" class="ts-reward-chip" data-reward="3">+3</button>
                                <input type="number" id="ts-reward-custom" class="ts-input ts-reward-input"
                                       placeholder="1–10" min="1" max="10" enterkeyhint="done">
                            </div>
                            <p class="ts-hint">Дополнительных билетов за выполнение (не более 10)</p>
                        </div>

                        <!-- Кнопки формы -->
                        <div class="ts-form-actions">
                            <button type="button" class="ts-cancel-task-btn" id="ts-cancel-task-form">
                                Отмена
                            </button>
                            <button type="button" class="ts-add-task-btn" id="ts-add-task-confirm">
                                Добавить задание
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Кнопка открытия формы -->
                <button type="button" class="ts-new-task-btn" id="ts-new-task-btn">
                    + Добавить задание
                </button>
            </div>

            <!-- Отступ под кнопку -->
            <div class="ts-bottom-spacer"></div>
        </div>

        <!-- Pop-up подтверждения удаления -->
        <div class="ts-delete-overlay" id="ts-delete-overlay" style="display:none">
            <div class="ts-delete-sheet" id="ts-delete-sheet">
                <p class="ts-delete-title">Удалить задание?</p>
                <p class="ts-delete-text">Это действие нельзя отменить.</p>
                <div class="ts-delete-actions">
                    <button type="button" class="ts-delete-btn ts-delete-btn--cancel" id="ts-delete-cancel">
                        Отмена
                    </button>
                    <button type="button" class="ts-delete-btn ts-delete-btn--confirm" id="ts-delete-confirm">
                        Удалить
                    </button>
                </div>
            </div>
        </div>

        <!-- Фиксированная кнопка «К оформлению» -->
        <div class="ts-footer" id="ts-footer">
            <button type="button" class="ts-checkout-btn ts-checkout-btn--inactive"
                    id="ts-checkout-btn">
                К оформлению
            </button>
        </div>
    `;
}
