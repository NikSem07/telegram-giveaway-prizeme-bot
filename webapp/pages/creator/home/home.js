// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';

// Утилита для определения окружения
function getTelegramEnvironment() {
  const tg = window.Telegram?.WebApp;
  
  if (!tg) {
    return 'external'; // Не в Telegram
  }
  
  const platform = tg.platform || 'unknown';
  const version = tg.version || '0';
  
  // Определяем по user agent и платформе
  const isMobileApp = platform === 'android' || platform === 'ios' || platform === 'tdesktop';
  const isWebVersion = platform === 'web' || platform === 'unknown';
  
  // Проверяем по user agent
  const ua = navigator.userAgent.toLowerCase();
  const isInTelegramWebApp = ua.includes('telegram') || ua.includes('webview');
  
  if (isMobileApp) {
    return 'mobile_app';
  } else if (isWebVersion && isInTelegramWebApp) {
    return 'telegram_web';
  } else {
    return 'external_browser';
  }
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
  const tg = window.Telegram?.WebApp;
  const env = getTelegramEnvironment();
  
  console.log(`[CreatorHome] Opening link in environment: ${env}`, url);
  
  switch (env) {
    case 'mobile_app':
      // В мобильном приложении Telegram - используем Telegram API
      try {
        if (typeof tg.openLink === 'function') {
          tg.openLink(url);
          return true;
        }
      } catch (e) {
        console.warn('[CreatorHome] tg.openLink failed, trying fallback:', e);
      }
      // Fallback для мобильного приложения
      window.location.href = url;
      return true;
      
    case 'telegram_web':
      // В веб-версии Telegram (telegram.org) - сложный случай
      // Пробуем разные методы
      try {
        // Метод 1: Telegram API
        if (typeof tg.openLink === 'function') {
          tg.openLink(url);
          return true;
        }
        
        // Метод 2: Через window.open с определенным таргетом
        const newWindow = window.open('', '_blank');
        if (newWindow) {
          newWindow.opener = null;
          newWindow.location = url;
          return true;
        }
        
        // Метод 3: location.href с задержкой
        setTimeout(() => {
          window.location.href = url;
        }, 100);
        return true;
        
      } catch (e) {
        console.error('[CreatorHome] All methods failed in Telegram Web:', e);
        window.open(url, '_blank');
        return false;
      }
      
    case 'external_browser':
    default:
      // Вне Telegram - обычное открытие
      window.open(url, '_blank');
      return false;
  }
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
    // молча: оставим "--"
    console.log('[CreatorHome] total giveaways load failed:', e);
  }
}

function attachEventListeners(container) {
  // Big card: create giveaway (у тебя уже есть window.createGiveaway)
  container.querySelector('[data-creator-action="create"]')?.addEventListener('click', () => {
    showCreateGiveawayModal();
  });

  // Donate
  container.querySelector('[data-creator-action="donate"]')?.addEventListener('click', () => {
    openTMAStartApp('dA1o');
  });

  // Subscribe
  container.querySelector('[data-creator-action="subscribe"]')?.addEventListener('click', () => {
    openTMAStartApp('sHOW');
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
    // Открываем бота с командой /create
    const botUrl = 'https://t.me/prizeme_official_bot?start=create';
  
    const env = getTelegramEnvironment();
  
    if (env === 'mobile_app') {
      // В мобильном приложении - закрываем Mini-App и открываем бота
      const tg = window.Telegram?.WebApp;
      if (tg?.close) {
        // Даем время на обработку открытия ссылки
        setTimeout(() => {
          tg.close();
        }, 100);
      }
    }
  
    // Открываем ссылку
    openTelegramLink(botUrl);
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

