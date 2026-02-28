// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';

// Утилита для определения окружения
function isInTelegramWebApp() {
  // Проверяем наличие Telegram WebApp объекта
  const tg = window.Telegram?.WebApp;
  if (!tg) return false;
  
  // Проверяем по user agent
  const ua = navigator.userAgent.toLowerCase();
  const hasTelegramUA = ua.includes('telegram') || ua.includes('webview');
  
  // Проверяем наличие initData (есть только в TMA)
  const hasInitData = !!tg.initData || !!tg.initDataUnsafe;
  
  return hasTelegramUA && hasInitData;
}

// Функция открытия через tg:// протокол (работает внутри Telegram)
function openInTelegram(url, fallbackUrl = null) {
  const tg = window.Telegram?.WebApp;
  
  console.log('[CreatorHome] openInTelegram called:', url);
  
  // Если есть Telegram WebApp API и openLink - используем его
  if (tg && typeof tg.openLink === 'function') {
    try {
      tg.openLink(url);
      return true;
    } catch (e) {
      console.warn('[CreatorHome] tg.openLink failed:', e);
    }
  }
  
  // Пробуем открыть через tg:// протокол
  if (url.startsWith('https://t.me/')) {
    // Конвертируем https://t.me/ ссылку в tg://
    const protocolUrl = url.replace('https://t.me/', 'tg://resolve?domain=');
    
    // Открываем протокольную ссылку
    const link = document.createElement('a');
    link.href = protocolUrl;
    link.style.display = 'none';
    document.body.appendChild(link);
    
    try {
      link.click();
      
      // Проверяем через 500мс, сработало ли
      setTimeout(() => {
        if (document.hidden === false && fallbackUrl) {
          console.log('[CreatorHome] Protocol link failed, using fallback');
          window.open(fallbackUrl, '_blank');
        }
      }, 500);
      
      return true;
    } catch (e) {
      console.warn('[CreatorHome] Protocol link failed:', e);
    } finally {
      if (link.parentNode) {
        link.parentNode.removeChild(link);
      }
    }
  }
  
  // Если ничего не сработало, используем fallback или стандартное открытие
  if (fallbackUrl) {
    window.open(fallbackUrl, '_blank');
  } else {
    window.open(url, '_blank');
  }
  
  return false;
}

// Специальные функции для TMA Tribute
function openTributeStartApp(startappParam) {
  // Две версии ссылки:
  const webUrl = `https://t.me/tribute/app?startapp=${startappParam}`;
  const protocolUrl = `tg://t.me/tribute/app?startapp=${startappParam}`;
  
  console.log(`[CreatorHome] Opening Tribute with startapp: ${startappParam}`);
  
  return openInTelegram(protocolUrl, webUrl);
}

// Функция для открытия бота
function openBotWithStart(startParam = '') {
  const botUsername = 'prizeme_official_bot';
  const webUrl = `https://t.me/${botUsername}${startParam ? `?start=${startParam}` : ''}`;
  const protocolUrl = `tg://resolve?domain=${botUsername}${startParam ? `&start=${startParam}` : ''}`;
  
  console.log(`[CreatorHome] Opening bot: ${botUsername}, start: ${startParam}`);
  
  return openInTelegram(protocolUrl, webUrl);
}


// API helper (минимальный, чтобы не зависеть от других модулей)
async function api(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return await res.json();
}

function getInitDataSafe() {
  const tg = window.Telegram?.WebApp;

  let init_data = tg?.initData || '';

  // fallback на sessionStorage как у тебя уже сделано в других местах
  if (!init_data) {
    try {
      const stored = sessionStorage.getItem('prizeme_init_data');
      if (stored) init_data = stored;
    } catch (e) {}
  }

  return init_data || '';
}

function openTelegramLink(url) {
  console.log('[CreatorHome] openTelegramLink (legacy) called:', url);
  
  // Для совместимости со старым кодом
  // Пытаемся определить, что за ссылка
  if (url.includes('tribute/app')) {
    // Это Tribute - используем специальную функцию
    const match = url.match(/startapp=(\w+)/);
    if (match) {
      return openTributeStartApp(match[1]);
    }
  } else if (url.includes('prizeme_official_bot')) {
    // Это наш бот
    const match = url.match(/start=(\w+)/);
    return openBotWithStart(match ? match[1] : '');
  }
  
  // Для других ссылок - используем общий метод
  return openInTelegram(url);
}


async function loadCreatorTotalGiveaways() {
  const init_data = getInitDataSafe();
  if (!init_data) return null;

  const data = await api('/api/creator_total_giveaways', { init_data });
  if (!data || !data.ok) return null;

  const n = Number(data.total_giveaways);
  return Number.isFinite(n) ? n : null;
}

export async function renderCreatorHomePage() {
  const main = document.getElementById('main-content');
  if (!main) return;

  // 1) Рендерим сразу каркас (чтобы UI мгновенно появился)
  main.innerHTML = creatorHomeTemplate({ totalGiveaways: null });
  attachEventListeners(main);

  // 2) Подгружаем число и обновляем только текст
  try {
    const total = await loadCreatorTotalGiveaways();
    const el = main.querySelector('#creator-total-giveaways');
    if (el && total !== null) el.textContent = String(total);
  } catch (e) {
    console.log('[CreatorHome] total giveaways load failed:', e);
  }

  // 3) Загружаем каналы
  attachChannelBlockListeners(main);
  renderChannelsList(main);
}

function attachEventListeners(container) {
    // Donate
    container.querySelector('[data-creator-action="donate"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[CreatorHome] Donate button clicked');
    openTributeStartApp('dA1o');
    });

    // Subscribe
    container.querySelector('[data-creator-action="subscribe"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[CreatorHome] Subscribe button clicked');
    openTributeStartApp('sHOW');
    });

    // Create giveaway
    container.querySelector('[data-creator-action="create"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[CreatorHome] Create giveaway button clicked');
    showCreateGiveawayModal();
    });
}

function showCreateGiveawayModal() {
  // Проверяем, есть ли уже модальное окно
  const existingModal = document.getElementById('create-giveaway-modal');
  if (existingModal) {
    existingModal.remove();
  }
  
  const modalHTML = `
    <div class="modal-overlay" id="create-giveaway-modal" style="
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    ">
      <div style="
        background: rgba(255, 255, 255, 0.06);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 24px;
        max-width: 320px;
        width: 100%;
        color: white;
        font-family: Roboto, system-ui, -apple-system, sans-serif;
      ">
        <h3 style="
          margin: 0 0 16px 0;
          font-size: 18px;
          font-weight: 600;
          text-align: center;
        ">Создание розыгрыша</h3>
        
        <p style="
          margin: 0 0 24px 0;
          font-size: 14px;
          line-height: 1.5;
          opacity: 0.9;
          text-align: center;
        ">
          Для создания розыгрыша Вас перекинет в бота @prizeme_official_bot
        </p>
        
        <div style="
          display: flex;
          gap: 12px;
          justify-content: center;
        ">
          <button type="button" class="modal-btn-cancel" style="
            flex: 1;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 12px;
            padding: 12px;
            color: white;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
          ">Отмена</button>
          
          <button type="button" class="modal-btn-confirm" style="
            flex: 1;
            background: linear-gradient(180deg, #2f7cff 0%, #1b4dff 100%);
            border: none;
            border-radius: 12px;
            padding: 12px;
            color: white;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
          ">Создать</button>
        </div>
      </div>
    </div>
  `;
  
  document.body.insertAdjacentHTML('beforeend', modalHTML);
  
  const modal = document.getElementById('create-giveaway-modal');
  
  // Обработчики событий
  modal.querySelector('.modal-btn-cancel').addEventListener('click', () => {
    modal.remove();
  });
  
    modal.querySelector('.modal-btn-confirm').addEventListener('click', () => {
    console.log('[CreatorHome] Create confirmation clicked');
    
    // Закрываем модальное окно
    modal.remove();
    
    // Небольшая задержка для анимации закрытия
    setTimeout(() => {
        // Открываем бота с командой create
        openBotWithStart('create');
    }, 200);
    });
  
  // Закрытие по клику на overlay
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.remove();
    }
  });
  
  // Закрытие по Escape
  const handleEscape = (e) => {
    if (e.key === 'Escape') {
      modal.remove();
      document.removeEventListener('keydown', handleEscape);
    }
  };
  document.addEventListener('keydown', handleEscape);
}

// Альтернативный метод открытия ссылок для веб-версии Telegram
function openLinkInTelegramWeb(url) {
  console.log('[CreatorHome] Using Telegram Web fallback method');
  
  // Создаем скрытый iframe для открытия ссылки
  const iframe = document.createElement('iframe');
  iframe.style.display = 'none';
  iframe.src = url;
  document.body.appendChild(iframe);
  
  // Удаляем через 2 секунды
  setTimeout(() => {
    if (iframe.parentNode) {
      iframe.parentNode.removeChild(iframe);
    }
  }, 2000);
  
  return true;
}

// Универсальная функция для открытия TMA Tribute
function openTMAStartApp(startappParam) {
  const url = `https://t.me/tribute/app?startapp=${startappParam}`;
  const env = getTelegramEnvironment();
  
  console.log(`[CreatorHome] Opening TMA with startapp: ${startappParam} in ${env}`);
  
  // Для веб-версии Telegram используем специальный метод
  if (env === 'telegram_web') {
    return openLinkInTelegramWeb(url);
  }
  
  // Для остальных - обычный метод
  return openTelegramLink(url);
}

// ================================================================
// БЛОК "МОИ КАНАЛЫ"
// ================================================================

async function loadChannels() {
  const init_data = getInitDataSafe();
  if (!init_data) return [];
  const data = await api('/api/creator_channels', { init_data });
  return data.ok ? data.channels : [];
}

function getMemberLabel(channel) {
  const type = channel.channel_type;
  const isGroup = type === 'group' || type === 'supergroup';
  const label = isGroup ? 'Участников' : 'Подписчиков';
  const count = channel.member_count !== null ? channel.member_count.toLocaleString('ru-RU') : '—';
  return `${label}: ${count}`;
}

function renderChannelAvatar(channel) {
  const letter = (channel.title || '?')[0].toUpperCase();
  return `
    <div class="ch-item-avatar">
      <img
        src="${channel.avatar_url}"
        alt=""
        onerror="this.parentNode.innerHTML='<div class=\\'ch-item-avatar-placeholder\\'>${letter}</div>'"
      />
    </div>
  `;
}

function renderChannelItem(channel) {
  return `
    <div class="ch-item" data-channel-id="${channel.id}">
      ${renderChannelAvatar(channel)}
      <div class="ch-item-info">
        <div class="ch-item-name">${channel.title}</div>
        <div class="ch-item-meta" id="ch-meta-${channel.id}">${getMemberLabel(channel)}</div>
      </div>
      <div class="ch-item-btns">
        <button class="ch-item-btn ch-item-btn--refresh" type="button"
          data-channel-id="${channel.id}" title="Обновить">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        </button>
        <button class="ch-item-btn ch-item-btn--delete" type="button"
          data-channel-id="${channel.id}"
          data-channel-title="${channel.title}"
          data-channel-type="${channel.channel_type}"
          title="Удалить">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
        </button>
      </div>
    </div>
  `;
}

async function renderChannelsList(container) {
  const list = container.querySelector('#ch-list');
  if (!list) return;

  list.innerHTML = '<div class="ch-loading">Загрузка...</div>';

  try {
    const channels = await loadChannels();

    if (!channels.length) {
      list.innerHTML = '<div class="ch-empty">Нет подключённых каналов</div>';
      return;
    }

    list.innerHTML = channels.map(renderChannelItem).join('');
    attachChannelItemListeners(container);
  } catch (e) {
    list.innerHTML = '<div class="ch-empty">Ошибка загрузки</div>';
    console.error('[Channels] load error:', e);
  }
}

function attachChannelItemListeners(container) {
  // Обновить конкретный канал
  container.querySelectorAll('.ch-item-btn--refresh').forEach(btn => {
    btn.addEventListener('click', async () => {
      const channelId = btn.dataset.channelId;
      btn.classList.add('ch-item-btn--spinning');
      btn.disabled = true;

      try {
        const init_data = getInitDataSafe();
        const data = await api('/api/creator_channel_refresh', { init_data, channel_id: channelId });

        if (data.ok) {
          const meta = container.querySelector(`#ch-meta-${channelId}`);
          if (meta) {
            const isGroup = data.channel_type === 'group' || data.channel_type === 'supergroup';
            const label = isGroup ? 'Участников' : 'Подписчиков';
            const count = data.member_count !== null ? Number(data.member_count).toLocaleString('ru-RU') : '—';
            meta.textContent = `${label}: ${count}`;
          }
        }
      } catch (e) {
        console.error('[Channels] refresh error:', e);
      } finally {
        btn.classList.remove('ch-item-btn--spinning');
        btn.disabled = false;
      }
    });
  });

  // Удалить канал
  container.querySelectorAll('.ch-item-btn--delete').forEach(btn => {
    btn.addEventListener('click', () => {
      const channelId = btn.dataset.channelId;
      const title = btn.dataset.channelTitle;
      const type = btn.dataset.channelType;
      const isGroup = type === 'group' || type === 'supergroup';
      const entityWord = isGroup ? 'группу' : 'канал';
      const entityWordFrom = isGroup ? 'группы' : 'канала';

      showChannelPopup({
        title: `Удалить ${entityWord}?`,
        subtitle: `Вы сможете вернуть ${entityWordFrom} «${title}» в любое время`,
        confirmText: 'Удалить',
        isDanger: true,
        onConfirm: async () => {
          try {
            const init_data = getInitDataSafe();
            const data = await api('/api/creator_channel_delete', { init_data, channel_id: channelId });
            if (data.ok) {
              const item = container.querySelector(`.ch-item[data-channel-id="${channelId}"]`);
              item?.remove();

              const list = container.querySelector('#ch-list');
              if (list && !list.querySelector('.ch-item')) {
                list.innerHTML = '<div class="ch-empty">Нет подключённых каналов</div>';
              }
            }
          } catch (e) {
            console.error('[Channels] delete error:', e);
          }
        }
      });
    });
  });
}

function attachChannelBlockListeners(container) {
  // Обновить все
  container.querySelector('#ch-refresh-all')?.addEventListener('click', async () => {
    const btn = container.querySelector('#ch-refresh-all');
    btn.classList.add('ch-header-btn--spinning');
    btn.disabled = true;
    await renderChannelsList(container);
    btn.classList.remove('ch-header-btn--spinning');
    btn.disabled = false;
  });

  // Добавить канал/группу
  container.querySelector('#ch-add')?.addEventListener('click', () => {
    showChannelPopup({
      title: 'Добавить канал / группу?',
      subtitle: 'Вас перекинет в бот, после чего вы сможете вернуться обратно в mini-app',
      confirmText: 'Да',
      onConfirm: () => {
        openBotWithStart('add_channel');
      }
    });
  });
}

function showChannelPopup({ title, subtitle, confirmText = 'Да', isDanger = false, onConfirm }) {
  const existing = document.getElementById('ch-popup');
  if (existing) existing.remove();

  const html = `
    <div class="ch-popup-overlay" id="ch-popup">
      <div class="ch-popup-sheet">
        <p class="ch-popup-title">${title}</p>
        <p class="ch-popup-subtitle">${subtitle}</p>
        <div class="ch-popup-actions">
          <button class="ch-popup-btn ch-popup-btn--cancel" type="button">Отмена</button>
          <button class="ch-popup-btn ch-popup-btn--confirm ${isDanger ? 'ch-popup-btn--confirm-danger' : ''}" type="button">${confirmText}</button>
        </div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', html);
  const overlay = document.getElementById('ch-popup');

  const close = () => {
    overlay.classList.remove('is-visible');
    overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
  };

  requestAnimationFrame(() => overlay.classList.add('is-visible'));

  overlay.querySelector('.ch-popup-btn--cancel').addEventListener('click', close);
  overlay.querySelector('.ch-popup-btn--confirm').addEventListener('click', () => {
    close();
    onConfirm?.();
  });
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
}
