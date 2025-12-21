// webapp/pages/creator/home/home.js
import creatorHomeTemplate from './home.template.js';

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
  
  if (!tg) {
    // Если не в TMA, открываем в новой вкладке
    window.open(url, '_blank');
    return;
  }
  
  try {
    // Пытаемся использовать Telegram WebApp API
    if (typeof tg.openLink === 'function') {
      tg.openLink(url);
      return;
    }
    
    // Если нет openLink, пробуем через window.open
    if (typeof tg.platform === 'string' && tg.platform !== 'unknown') {
      // Мы в мобильном клиенте Telegram
      window.location.href = url;
    } else {
      // Веб-версия или десктоп
      window.open(url, '_blank');
    }
  } catch (error) {
    console.warn('[CreatorHome] Failed to open link via Telegram API:', error);
    // Fallback
    window.open(url, '_blank');
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
    openTelegramLink('https://t.me/tribute/app?startapp=dA1o');
  });

  // Subscribe
  container.querySelector('[data-creator-action="subscribe"]')?.addEventListener('click', () => {
    openTelegramLink('https://t.me/tribute/app?startapp=sHOW');
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
    // Закрываем мини-апп (если в TMA)
    const tg = window.Telegram?.WebApp;
    if (tg?.close) {
      tg.close();
    }
    
    // Открываем бота с командой /create
    const botUrl = 'https://t.me/prizeme_official_bot?start=create';
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
