// CAPTCHA PAGE LOGIC

// Глобальные переменные
let captchaToken = null;
let giveawayId = null;

// Инициализация страницы
function initializeCaptchaPage() {
    console.log('[CAPTCHA] Initializing captcha page');
    
    // Получаем ID розыгрыша из sessionStorage
    giveawayId = sessionStorage.getItem('prizeme_gid');
    if (!giveawayId) {
        console.error('[CAPTCHA] No giveaway ID found');
        showError('Не удалось определить розыгрыш');
        return;
    }
    
    console.log(`[CAPTCHA] Giveaway ID: ${giveawayId}`);
    
    // Проверяем тестовый режим
    checkTestMode();
    
    // Загружаем виджет Captcha
    loadCaptchaWidget();
}

// Проверяем тестовый режим
async function checkTestMode() {
    try {
        const response = await fetch('/api/captcha_config');
        if (response.ok) {
            const data = await response.json();
            if (data.test_mode || data.site_key === '1x00000000000000000000AA') {
                document.getElementById('test-mode-notice').style.display = 'block';
            }
        }
    } catch (error) {
        console.log('[CAPTCHA] Error checking test mode:', error);
    }
}

// Загружает виджет Captcha
function loadCaptchaWidget() {
    console.log('[CAPTCHA] Loading captcha widget');
    
    // 🔄 В тестовом режиме показываем заглушку
    // В реальной реализации здесь будет загрузка Cloudflare Turnstile
    
    const widgetContainer = document.getElementById('turnstile-widget');
    widgetContainer.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">🛡️</div>
            <div style="color: #a0a0a0; font-size: 14px;">
                В тестовом режиме проверка Captcha пропускается автоматически.<br>
                Нажмите "Проверить" чтобы продолжить.
            </div>
        </div>
    `;
    
    // В тестовом режиме автоматически "проходим" Captcha
    setTimeout(() => {
        captchaToken = 'test_token_' + Date.now();
        console.log('[CAPTCHA] Test token generated:', captchaToken);
    }, 1000);
}

// Проверяет Captcha
async function verifyCaptcha() {
    console.log('[CAPTCHA] Starting verification');
    
    if (!captchaToken) {
        showError('Пожалуйста, пройдите проверку безопасности');
        return;
    }
    
    // Показываем индикатор загрузки
    const button = document.getElementById('verify-button');
    const buttonText = document.getElementById('button-text');
    const buttonLoading = document.getElementById('button-loading');
    
    button.disabled = true;
    buttonText.textContent = 'Проверяем...';
    buttonLoading.style.display = 'inline-block';
    
    // Скрываем предыдущие сообщения
    hideError();
    hideSuccess();
    
    try {
        // Проверяем токен через API
        const isValid = await verifyCaptchaToken(captchaToken, giveawayId);
        
        if (isValid) {
            console.log('[CAPTCHA] Verification successful');
            showSuccess();
            
            // Ждем немного чтобы пользователь увидел успех
            setTimeout(() => {
                // Вызываем функцию обработки успешной Captcha из app.js
                if (typeof handleCaptchaSuccess === 'function') {
                    handleCaptchaSuccess(giveawayId, captchaToken);
                } else {
                    // Фоллбек: возвращаем к основному flow
                    sessionStorage.setItem('prizeme_captcha_verified', 'true');
                    window.location.href = '/miniapp/loading';
                }
            }, 1000);
        } else {
            console.log('[CAPTCHA] Verification failed');
            showError('Проверка не пройдена. Попробуйте еще раз.');
            resetButton();
        }
        
    } catch (error) {
        console.error('[CAPTCHA] Verification error:', error);
        showError('Ошибка при проверке. Попробуйте еще раз.');
        resetButton();
    }
}

// Вспомогательные функции UI
function showError(message) {
    const errorEl = document.getElementById('error-message');
    errorEl.textContent = message || '❌ Ошибка проверки. Пожалуйста, попробуйте еще раз.';
    errorEl.style.display = 'block';
}

function hideError() {
    document.getElementById('error-message').style.display = 'none';
}

function showSuccess() {
    document.getElementById('success-message').style.display = 'block';
}

function hideSuccess() {
    document.getElementById('success-message').style.display = 'none';
}

function resetButton() {
    const button = document.getElementById('verify-button');
    const buttonText = document.getElementById('button-text');
    const buttonLoading = document.getElementById('button-loading');
    
    button.disabled = false;
    buttonText.textContent = 'Проверить';
    buttonLoading.style.display = 'none';
}

function goBack() {
    window.history.back();
}

// Инициализируем страницу при загрузке
document.addEventListener('DOMContentLoaded', initializeCaptchaPage);