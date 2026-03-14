// webapp/pages/creator/services/task-services.js
import taskServicesTemplate, { TASK_TYPES } from "./task-services.template.js";
import Router from "../../../shared/router.js";

// ── Константы ─────────────────────────────────────────────────────────────
const MAX_TASKS = 7;
const TASK_PRICE_RUB = 199;
const TASK_PRICE_STARS = 199;

// ── Состояние модуля ──────────────────────────────────────────────────────
// Используем объект-хранилище — сбрасывается при каждом рендере страницы
let _state = null;

function _freshState() {
  return {
    description: "",
    mediaUrl: null, // загруженный URL на сервере
    mediaFile: null, // локальный File объект (до загрузки)
    limitMode: "unlimited",
    limitValue: null,
    tasks: [], // массив готовых заданий
    formOpen: false, // открыта ли форма нового задания
    deletingIndex: null, // индекс задания на удаление

    // Текущее незавершённое задание в форме
    form: {
      type: null,
      title: "",
      link: "",
      secretEnabled: false,
      secret: "",
      reward: null, // число 1-10
    },
  };
}

// ── Утилиты ───────────────────────────────────────────────────────────────
function _getInitData() {
  return (
    window.Telegram?.WebApp?.initData ||
    sessionStorage.getItem("prizeme_init_data") ||
    ""
  );
}

function _typeInfo(typeId) {
  return TASK_TYPES.find((t) => t.id === typeId) || null;
}

function _isTelegramType(typeId) {
  const info = _typeInfo(typeId);
  return info?.group === "telegram";
}

// ── Счётчики символов ─────────────────────────────────────────────────────
function _updateDescCounter() {
  const el = document.getElementById("ts-desc-count");
  if (el) el.textContent = (_state.description || "").length;
}

function _updateTitleCounter() {
  const el = document.getElementById("ts-title-count");
  if (el) el.textContent = (_state.form.title || "").length;
}

// ── Кнопка «К оформлению» ────────────────────────────────────────────────
function _updateCheckoutBtn() {
  const btn = document.getElementById("ts-checkout-btn");
  if (!btn) return;
  const hasTask = _state.tasks.length > 0;
  btn.classList.toggle("ts-checkout-btn--inactive", !hasTask);
  btn.disabled = !hasTask;
}

// ── Кнопка «+ Добавить задание» ──────────────────────────────────────────
function _updateNewTaskBtn() {
  const btn = document.getElementById("ts-new-task-btn");
  if (!btn) return;
  const atMax = _state.tasks.length >= MAX_TASKS;
  btn.style.display = atMax ? "none" : "";
}

// ── Счётчик заданий ───────────────────────────────────────────────────────
function _updateTasksCount() {
  const el = document.getElementById("ts-tasks-count");
  if (el) el.textContent = `${_state.tasks.length}/${MAX_TASKS}`;
}

// ── Иконка типа задания ───────────────────────────────────────────────────
function _typeIcon(typeId) {
  const icons = {
    telegram_subscribe: "📢",
    telegram_comment: "💬",
    telegram_post: "👁",
    external_video: "▶️",
    external_post: "📄",
    external_subscribe: "➕",
    custom: "⚙️",
  };
  return icons[typeId] || "•";
}

// ── Рендер списка готовых заданий ─────────────────────────────────────────
function _renderTasksList() {
  const list = document.getElementById("ts-tasks-list");
  if (!list) return;

  if (_state.tasks.length === 0) {
    list.innerHTML = "";
    return;
  }

  list.innerHTML = _state.tasks
    .map(
      (task, i) => `
        <div class="ts-task-item" data-index="${i}">
            <div class="ts-task-item-num">${i + 1}</div>
            <div class="ts-task-item-info">
                <span class="ts-task-item-icon">${_typeIcon(task.type)}</span>
                <span class="ts-task-item-title">${_esc(task.title)}</span>
                <span class="ts-task-item-reward">+${task.reward} 🎟</span>
            </div>
            <button type="button" class="ts-task-item-delete" data-index="${i}"
                    aria-label="Удалить задание">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                    <path d="M10 11v6M14 11v6"/>
                    <path d="M9 6V4h6v2"/>
                </svg>
            </button>
        </div>
    `,
    )
    .join("");

  // Обработчики удаления
  list.querySelectorAll(".ts-task-item-delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.index);
      _openDeleteConfirm(idx);
    });
  });
}

// ── Эскейп HTML ───────────────────────────────────────────────────────────
function _esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Pop-up удаления ───────────────────────────────────────────────────────
function _openDeleteConfirm(index) {
  _state.deletingIndex = index;
  const overlay = document.getElementById("ts-delete-overlay");
  const sheet = document.getElementById("ts-delete-sheet");
  if (!overlay || !sheet) return;

  overlay.style.display = "flex";
  requestAnimationFrame(() => {
    overlay.classList.add("ts-delete-overlay--visible");
    sheet.classList.add("ts-delete-sheet--visible");
  });
}

function _closeDeleteConfirm() {
  _state.deletingIndex = null;
  const overlay = document.getElementById("ts-delete-overlay");
  const sheet = document.getElementById("ts-delete-sheet");
  if (!overlay || !sheet) return;

  overlay.classList.remove("ts-delete-overlay--visible");
  sheet.classList.remove("ts-delete-sheet--visible");
  sheet.addEventListener(
    "transitionend",
    () => {
      overlay.style.display = "none";
    },
    { once: true },
  );
}

function _confirmDelete() {
  const idx = _state.deletingIndex;
  if (idx === null || idx < 0 || idx >= _state.tasks.length) {
    _closeDeleteConfirm();
    return;
  }
  _state.tasks.splice(idx, 1);
  _closeDeleteConfirm();
  _renderTasksList();
  _updateTasksCount();
  _updateNewTaskBtn();
  _updateCheckoutBtn();
}

// ── Форма нового задания ──────────────────────────────────────────────────
function _openTaskForm() {
  // Сбрасываем форму
  _state.form = {
    type: null,
    title: "",
    link: "",
    secretEnabled: false,
    secret: "",
    reward: null,
  };
  _state.formOpen = true;

  const formEl = document.getElementById("ts-task-form");
  if (!formEl) return;

  // Сбрасываем поля
  const titleInput = document.getElementById("ts-task-title");
  const linkInput = document.getElementById("ts-task-link");
  const secretInput = document.getElementById("ts-task-secret");
  const rewardInput = document.getElementById("ts-reward-custom");

  if (titleInput) titleInput.value = "";
  if (linkInput) linkInput.value = "";
  if (secretInput) secretInput.value = "";
  if (rewardInput) rewardInput.value = "";

  // Сбрасываем селектор группы и чипы
  const groupSelectLabel = document.getElementById("ts-group-select-label");
  const groupSelectBtn = document.getElementById("ts-group-select-btn");
  const chipsBlock = document.getElementById("ts-type-chips-block");
  const chipsContainer = document.getElementById("ts-type-chips-container");
  if (groupSelectLabel) groupSelectLabel.textContent = "Выберите тип задания";
  if (groupSelectBtn)
    groupSelectBtn.classList.remove("ts-group-select-btn--selected");
  if (chipsBlock) chipsBlock.classList.remove("ts-type-chips-block--visible");
  if (chipsContainer) chipsContainer.innerHTML = "";
  document
    .getElementById("ts-group-dropdown")
    ?.classList.remove("ts-group-dropdown--open");
  document
    .getElementById("ts-group-select-arrow")
    ?.classList.remove("ts-group-select-arrow--open");
  // Сбрасываем чипы награды
  document
    .querySelectorAll(".ts-reward-chip")
    .forEach((c) => c.classList.remove("ts-reward-chip--active"));
  // Скрываем секретный код
  document.getElementById("ts-field-secret").style.display = "none";
  document.getElementById("ts-secret-input-wrap").style.display = "none";
  _state.form.secretEnabled = false;

  // Показываем форму с анимацией
  formEl.style.display = "";
  requestAnimationFrame(() => formEl.classList.add("ts-task-form--open"));

  // Скрываем кнопку «+ Добавить задание» пока форма открыта
  document.getElementById("ts-new-task-btn").style.display = "none";

  _updateTitleCounter();

  // Скроллим к форме
  setTimeout(() => {
    formEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, 120);
}

function _closeTaskForm() {
  _state.formOpen = false;
  const formEl = document.getElementById("ts-task-form");
  if (!formEl) return;

  formEl.classList.remove("ts-task-form--open");
  formEl.addEventListener(
    "transitionend",
    () => {
      formEl.style.display = "none";
      // Показываем кнопку «+ Добавить» если лимит не достигнут
      _updateNewTaskBtn();
    },
    { once: true },
  );
}

// ── Валидация формы задания ───────────────────────────────────────────────
function _validateForm() {
  const f = _state.form;

  if (!f.type) {
    _showFormError("Выберите тип задания");
    return false;
  }
  if (!f.title.trim()) {
    _showFormError("Введите название задания");
    return false;
  }
  if (!f.link.trim()) {
    _showFormError("Введите ссылку на задание");
    return false;
  }
  // Проверка ссылки — для telegram_subscribe принимаем @username
  const linkVal = f.link.trim();
  if (f.type === "telegram_subscribe") {
    if (
      !linkVal.startsWith("@") &&
      !linkVal.match(/(?:https?:\/\/)?t\.me\/[a-zA-Z0-9_]+/)
    ) {
      _showFormError(
        "Введите ссылку в формате https://t.me/channel или @username",
      );
      return false;
    }
  } else {
    try {
      new URL(linkVal);
    } catch (_) {
      _showFormError("Ссылка должна начинаться с https://");
      return false;
    }
  }
  if (f.secretEnabled && !f.secret.trim()) {
    _showFormError("Введите секретный код или отключите его");
    return false;
  }
  if (!f.reward || f.reward < 1 || f.reward > 10) {
    _showFormError("Укажите награду от 1 до 10 билетов");
    return false;
  }
  return true;
}

function _showFormError(msg) {
  // Удаляем старый тост если есть
  document.getElementById("ts-form-error")?.remove();

  const toast = document.createElement("div");
  toast.id = "ts-form-error";
  toast.className = "ts-toast ts-toast--error";
  toast.textContent = msg;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("ts-toast--visible"));

  setTimeout(() => {
    toast.classList.remove("ts-toast--visible");
    toast.addEventListener("transitionend", () => toast.remove(), {
      once: true,
    });
  }, 2800);
}

// ── Подтверждение добавления задания ─────────────────────────────────────
function _confirmAddTask() {
  if (!_validateForm()) return;

  const f = _state.form;
  _state.tasks.push({
    type: f.type,
    title: f.title.trim(),
    link: f.link.trim(),
    secret: f.secretEnabled ? f.secret.trim() : null,
    reward: f.reward,
  });

  _closeTaskForm();

  // Небольшая задержка — ждём закрытия формы перед ре-рендером
  setTimeout(() => {
    _renderTasksList();
    _updateTasksCount();
    _updateNewTaskBtn();
    _updateCheckoutBtn();
  }, 300);
}

// ── Загрузка медиа ────────────────────────────────────────────────────────
async function _uploadMedia(file) {
  const initData = _getInitData();
  const formData = new FormData();
  formData.append("media", file);
  formData.append("init_data", initData);

  try {
    const resp = await fetch("/api/task_upload_media", {
      method: "POST",
      body: formData,
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.reason || "upload_failed");
    return data.url;
  } catch (e) {
    console.error("[TASK_SERVICES] uploadMedia error:", e);
    throw e;
  }
}

// ── Сохранение состояния в sessionStorage (для чекаута) ───────────────────
function _saveToSession() {
  try {
    sessionStorage.setItem(
      "prizeme_task_pool",
      JSON.stringify({
        description: _state.description,
        mediaUrl: _state.mediaUrl,
        limitMode: _state.limitMode,
        limitValue: _state.limitValue,
        tasks: _state.tasks,
        pricePerTask: { rub: TASK_PRICE_RUB, stars: TASK_PRICE_STARS },
      }),
    );
  } catch (e) {
    console.warn("[TASK_SERVICES] failed to save state to session:", e);
  }
}

// ── Инициализация обработчиков ────────────────────────────────────────────
function _initHandlers() {
  // --- Подсказка у заголовка «Лимит участников» ---
  const limitHintBtn = document.getElementById("ts-limit-hint-btn");
  const limitHintTooltip = document.getElementById("ts-limit-hint-tooltip");

  limitHintBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    limitHintTooltip?.classList.toggle("ts-hint-tooltip--visible");
  });

  document.addEventListener("click", function _closeLimitTooltip(e) {
    if (!limitHintBtn?.contains(e.target)) {
      limitHintTooltip?.classList.remove("ts-hint-tooltip--visible");
    }
  });

  // --- Описание ---
  const descInput = document.getElementById("ts-description");
  if (descInput) {
    descInput.addEventListener("input", () => {
      // Убираем переносы строк
      const clean = descInput.value.replace(/[\r\n]+/g, " ");
      _state.description = clean.slice(0, 100);
      descInput.value = _state.description;
      _updateDescCounter();
    });
    descInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        descInput.blur();
      }
    });
  }

  // --- Лимит: переключение ---
  document
    .getElementById("ts-limit-unlimited")
    ?.addEventListener("click", () => {
      _state.limitMode = "unlimited";
      document
        .getElementById("ts-limit-unlimited")
        .classList.add("ts-limit-btn--active");
      document
        .getElementById("ts-limit-custom")
        .classList.remove("ts-limit-btn--active");
      document.getElementById("ts-limit-input-wrap").style.display = "none";
      _state.limitValue = null;
    });

  document.getElementById("ts-limit-custom")?.addEventListener("click", () => {
    _state.limitMode = "custom";
    document
      .getElementById("ts-limit-custom")
      .classList.add("ts-limit-btn--active");
    document
      .getElementById("ts-limit-unlimited")
      .classList.remove("ts-limit-btn--active");
    document.getElementById("ts-limit-input-wrap").style.display = "";
    document.getElementById("ts-limit-value")?.focus();
  });

  document.getElementById("ts-limit-value")?.addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    _state.limitValue = Number.isFinite(val) && val >= 1 ? val : null;
  });
  document
    .getElementById("ts-limit-value")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.target.blur();
      }
    });

  // --- Открытие формы нового задания ---
  document.getElementById("ts-new-task-btn")?.addEventListener("click", () => {
    if (_state.tasks.length >= MAX_TASKS) return;
    _openTaskForm();
  });

  // --- Тип задания: выпадающий список групп ---
  const groupSelectBtn = document.getElementById("ts-group-select-btn");
  const groupSelectLabel = document.getElementById("ts-group-select-label");
  const groupSelectArrow = document.getElementById("ts-group-select-arrow");
  const groupDropdown = document.getElementById("ts-group-dropdown");
  const chipsBlock = document.getElementById("ts-type-chips-block");
  const chipsContainer = document.getElementById("ts-type-chips-container");

  const GROUP_CHIPS = {
    telegram: [
      { id: "telegram_subscribe", label: "Подписка на канал" },
      { id: "telegram_comment", label: "Комментарий" },
      { id: "telegram_post", label: "Просмотр поста" },
    ],
    external: [
      { id: "external_video", label: "Просмотр видео" },
      { id: "external_post", label: "Пост в соцсетях" },
      { id: "external_subscribe", label: "Подписка на соцсети" },
    ],
    custom: [{ id: "custom", label: "Своё задание" }],
  };

  const GROUP_LABELS = {
    telegram: "В Telegram",
    external: "На внешних ресурсах",
    custom: "Кастомное",
  };

  let _dropdownOpen = false;

  function _toggleDropdown(open) {
    _dropdownOpen = open;
    groupDropdown.classList.toggle("ts-group-dropdown--open", open);
    groupSelectArrow.classList.toggle("ts-group-select-arrow--open", open);
  }

  function _selectGroup(groupId) {
    // Обновляем кнопку-селектор
    groupSelectLabel.textContent = GROUP_LABELS[groupId];
    groupSelectBtn.classList.add("ts-group-select-btn--selected");
    _toggleDropdown(false);

    // Сбрасываем тип и все зависимые поля формы
    _state.form.type = null;
    _state.form.link = "";
    _state.form.secretEnabled = false;
    _state.form.secret = "";

    const linkInput = document.getElementById("ts-task-link");
    const linkLabel = document.getElementById("ts-field-link-label");
    const botConnectField = document.getElementById("ts-field-bot-connect");
    const secretField = document.getElementById("ts-field-secret");
    const secretWrap = document.getElementById("ts-secret-input-wrap");
    const secretInp = document.getElementById("ts-task-secret");
    const secretLabel = document.getElementById("ts-secret-toggle-label");

    if (linkInput) {
      linkInput.value = "";
      linkInput.placeholder = "https://...";
    }
    if (linkLabel) linkLabel.textContent = "Ссылка на задание";
    if (botConnectField) botConnectField.style.display = "none";
    if (secretField) secretField.style.display = "none";
    if (secretWrap) secretWrap.style.display = "none";
    if (secretInp) secretInp.value = "";
    if (secretLabel) secretLabel.textContent = "Добавить секретный код";

    // Рендерим чипы
    const chips = GROUP_CHIPS[groupId] || [];
    chipsContainer.innerHTML = chips
      .map(
        (c) =>
          `<button type="button" class="ts-type-chip" data-type="${c.id}">${c.label}</button>`,
      )
      .join("");

    // Показываем блок чипов с анимацией
    chipsBlock.classList.add("ts-type-chips-block--visible");

    // Вешаем обработчики на новые чипы
    chipsContainer.querySelectorAll(".ts-type-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const typeId = chip.dataset.type;
        _state.form.type = typeId;

        chipsContainer
          .querySelectorAll(".ts-type-chip")
          .forEach((c) => c.classList.remove("ts-type-chip--active"));
        chip.classList.add("ts-type-chip--active");

        // Секретный код — только для external и custom
        const secretField = document.getElementById("ts-field-secret");
        if (_isTelegramType(typeId)) {
          secretField.style.display = "none";
          _state.form.secretEnabled = false;
          document.getElementById("ts-secret-input-wrap").style.display =
            "none";
        } else {
          secretField.style.display = "";
        }

        // Блок подключения бота и label ссылки
        const botConnectField = document.getElementById("ts-field-bot-connect");
        const linkLabel = document.getElementById("ts-field-link-label");
        if (typeId === "telegram_subscribe") {
          if (botConnectField) botConnectField.style.display = "";
          if (linkLabel)
            linkLabel.textContent = "Ссылка на канал или @username";
          document.getElementById("ts-task-link").placeholder =
            "https://t.me/channel или @username";
        } else {
          if (botConnectField) botConnectField.style.display = "none";
          if (linkLabel) linkLabel.textContent = "Ссылка на задание";
          document.getElementById("ts-task-link").placeholder = "https://...";
        }
      });
    });
  }

  groupSelectBtn?.addEventListener("click", () => {
    _toggleDropdown(!_dropdownOpen);
  });

  groupDropdown?.querySelectorAll(".ts-group-option").forEach((option) => {
    option.addEventListener("click", () => {
      _selectGroup(option.dataset.group);
    });
  });

  // Закрытие дропдауна при клике вне
  document.addEventListener(
    "click",
    (e) => {
      if (
        _dropdownOpen &&
        !groupSelectBtn.contains(e.target) &&
        !groupDropdown.contains(e.target)
      ) {
        _toggleDropdown(false);
      }
    },
    { capture: true },
  );

  // --- Название задания ---
  document.getElementById("ts-task-title")?.addEventListener("input", (e) => {
    const clean = e.target.value.replace(/[\r\n]+/g, " ");
    _state.form.title = clean.slice(0, 30);
    e.target.value = _state.form.title;
    _updateTitleCounter();
  });
  document.getElementById("ts-task-title")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.target.blur();
    }
  });

  // --- Ссылка ---
  document.getElementById("ts-task-link")?.addEventListener("input", (e) => {
    _state.form.link = e.target.value;
  });

  // --- Кнопка подключения бота к каналу ---
  document
    .getElementById("ts-bot-connect-btn")
    ?.addEventListener("click", () => {
      const tg = window.Telegram?.WebApp;
      const botUrl = "https://t.me/prizeme_official_bot?start=add_channel";
      if (tg?.openTelegramLink) tg.openTelegramLink(botUrl);
      else window.open(botUrl, "_blank");
    });

  document.getElementById("ts-task-link")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.target.blur();
    }
  });

  // --- Секретный код: toggle ---
  document.getElementById("ts-secret-toggle")?.addEventListener("click", () => {
    _state.form.secretEnabled = !_state.form.secretEnabled;
    const wrap = document.getElementById("ts-secret-input-wrap");
    const label = document.getElementById("ts-secret-toggle-label");
    if (_state.form.secretEnabled) {
      wrap.style.display = "";
      label.textContent = "Убрать секретный код";
      document.getElementById("ts-task-secret")?.focus();
    } else {
      wrap.style.display = "none";
      label.textContent = "Добавить секретный код";
      _state.form.secret = "";
      const inp = document.getElementById("ts-task-secret");
      if (inp) inp.value = "";
    }
  });

  document.getElementById("ts-task-secret")?.addEventListener("input", (e) => {
    // Только буквы, цифры, от 1 до 10 символов
    _state.form.secret = e.target.value
      .replace(/[^a-zA-Z0-9]/g, "")
      .slice(0, 10);
    e.target.value = _state.form.secret;
  });
  document
    .getElementById("ts-task-secret")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.target.blur();
      }
    });

  // --- Награда: чипы ---
  document.querySelectorAll(".ts-reward-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const val = parseInt(chip.dataset.reward);
      _state.form.reward = val;

      document
        .querySelectorAll(".ts-reward-chip")
        .forEach((c) => c.classList.remove("ts-reward-chip--active"));
      chip.classList.add("ts-reward-chip--active");

      const customInput = document.getElementById("ts-reward-custom");
      if (customInput) customInput.value = "";
    });
  });

  // --- Награда: произвольное число ---
  document
    .getElementById("ts-reward-custom")
    ?.addEventListener("input", (e) => {
      const val = parseInt(e.target.value);
      if (Number.isFinite(val) && val >= 1 && val <= 10) {
        _state.form.reward = val;
        document
          .querySelectorAll(".ts-reward-chip")
          .forEach((c) => c.classList.remove("ts-reward-chip--active"));
      } else {
        _state.form.reward = null;
      }
    });
  document
    .getElementById("ts-reward-custom")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.target.blur();
      }
    });

  // --- Подтвердить добавление задания ---
  document
    .getElementById("ts-add-task-confirm")
    ?.addEventListener("click", _confirmAddTask);

  // --- Отменить форму (кнопка «Отмена» внутри формы) ---
  document
    .getElementById("ts-cancel-task-form")
    ?.addEventListener("click", () => {
      _closeTaskForm();
    });

  // --- Pop-up удаления ---
  document
    .getElementById("ts-delete-cancel")
    ?.addEventListener("click", _closeDeleteConfirm);
  document
    .getElementById("ts-delete-confirm")
    ?.addEventListener("click", _confirmDelete);
  document
    .getElementById("ts-delete-overlay")
    ?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) _closeDeleteConfirm();
    });

  // --- К оформлению ---
  document.getElementById("ts-checkout-btn")?.addEventListener("click", () => {
    if (_state.tasks.length === 0) return;

    // Сохраняем состояние для чекаута
    _saveToSession();
    Router.navigate("task_services_checkout");
  });
}

// ── BackButton ────────────────────────────────────────────────────────────
// hide() сбрасывает ВСЕ обработчики onClick — это важно, чтобы не накапливались
// старые колбэки от предыдущих страниц (напр. preview → services)
function _showBackButton(onBack) {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  try {
    tg.BackButton.hide(); // сбрасываем все старые обработчики
    tg.BackButton.onClick(onBack);
    tg.BackButton.show();
  } catch (e) {}
}

function _hideBackButton(onBack) {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  try {
    tg.BackButton.offClick(onBack);
    tg.BackButton.hide();
  } catch (e) {}
}

// ── Управление шапкой и навбаром ─────────────────────────────────────────
function _setShellVisibility(visible) {
  const topHeader = document.querySelector(".top-header");
  if (topHeader) topHeader.style.display = visible ? "" : "none";
  if (visible) {
    document.body.classList.remove("page-checkout-services");
  } else {
    document.body.classList.add("page-checkout-services");
  }
}

// ── Основной рендер ───────────────────────────────────────────────────────
export function renderTaskServicesPage() {
  const main = document.getElementById("main-content");
  if (!main) return;

  // Скрываем шапку и навбар
  _setShellVisibility(false);

  // Каждый раз создаём свежее состояние
  _state = _freshState();

  window.scrollTo({ top: 0, behavior: "auto" });

  main.innerHTML = taskServicesTemplate();

  // BackButton → возврат на превью
  const handleBack = () => {
    _hideBackButton(handleBack);
    Router.navigate("task_services_preview");
  };
  _showBackButton(handleBack);

  _initHandlers();
  _updateDescCounter();
  _updateTitleCounter();
  _updateTasksCount();
  _updateCheckoutBtn();
  _updateNewTaskBtn();
}
