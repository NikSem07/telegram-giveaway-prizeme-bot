// CAPTCHA PAGE LOGIC - ПОЛНАЯ ИНТЕГРАЦИЯ С TELEGRAM WEBAPP

// Глобальные переменные
let captchaToken = null;
let giveawayId = null;
let userId = null;

// Инициализация страницы
function initializeCaptchaPage() {
    console.log('[CAPTCHA] Initializing captcha page with Telegram WebApp');
    
    // 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Получаем данные из Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (!tg) {
        console.error('[CAPTCHA] Telegram WebApp not found');
        showError('Ошибка загрузки приложения Telegram');
        return;
    }
    
    // Расширяем приложение на весь экран
    tg.expand();
    
    // 🔥 ИЗВЛЕКАЕМ ДАННЫЕ ИЗ TELEGRAM
    try {
        // 1. Извлекаем user_id из initData
        const initData = tg.initData || '';
        const params = new URLSearchParams(initData);
        const userEncoded = params.get('user');
        
        if (userEncoded) {
            const userJson = decodeURIComponent(userEncoded);
            const user = JSON.parse(userJson);
            userId = user.id;
            console.log(`[CAPTCHA] User ID extracted from Telegram: ${userId}`);
        } else {
            console.warn('[CAPTCHA] No user data in initData');
        }
        
        // 2. Получаем giveaway_id из start_param или sessionStorage
        const startParam = tg.initDataUnsafe?.start_param;
        if (startParam && startParam.startsWith('captcha_')) {
            giveawayId = startParam.replace('captcha_', '');
            console.log(`[CAPTCHA] Giveaway ID from start_param: ${giveawayId}`);
        } else {
            // Fallback: из sessionStorage
            giveawayId = sessionStorage.getItem('prizeme_gid');
            console.log(`[CAPTCHA] Giveaway ID from sessionStorage: ${giveawayId}`);
        }
        
        if (!giveawayId || !userId) {
            console.error('[CAPTCHA] Missing required data:', { giveawayId, userId });
            showError('Не удалось определить параметры розыгрыша');
            return;
        }
        
        // Сохраняем данные для дальнейшего использования
        sessionStorage.setItem('prizeme_gid', giveawayId);
        sessionStorage.setItem('prizeme_user_id', userId);
        
    } catch (error) {
        console.error('[CAPTCHA] Error parsing Telegram data:', error);
        showError('Ошибка загрузки данных. Пожалуйста, перезагрузите страницу.');
        return;
    }
    
    console.log(`[CAPTCHA] Ready: user_id=${userId}, giveaway_id=${giveawayId}`);
    
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
                console.log('[CAPTCHA] Test mode detected');
            }
        }
    } catch (error) {
        console.log('[CAPTCHA] Error checking test mode:', error);
    }
}

// Загружает виджет Cloudflare Turnstile Captcha
function loadCaptchaWidget() {
    console.log('[CAPTCHA] Loading Cloudflare Turnstile widget');
    
    // Получаем конфигурацию из API
    fetch('/api/captcha_config')
        .then(response => response.json())
        .then(config => {
            console.log('[CAPTCHA] Config received:', config);
            
            if (config.test_mode || !config.enabled) {
                // 🔄 ТЕСТОВЫЙ РЕЖИМ: показываем заглушку
                showTestWidget();
                return;
            }
            
            // 🔥 РЕАЛЬНЫЙ РЕЖИМ: загружаем Cloudflare Turnstile
            const siteKey = config.site_key;
            const widgetContainer = document.getElementById('turnstile-widget');
            
            // Очищаем контейнер
            widgetContainer.innerHTML = '<div id="cf-turnstile"></div>';
            
            // Добавляем скрипт Turnstile
            const script = document.createElement('script');
            script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
            script.async = true;
            script.defer = true;
            
            script.onload = () => {
                console.log('[CAPTCHA] Turnstile script loaded');
                
                // Рендерим виджет
                window.turnstile.render('#cf-turnstile', {
                    sitekey: siteKey,
                    theme: 'dark', // или 'light' в зависимости от темы
                    callback: function(token) {
                        console.log('[CAPTCHA] Turnstile callback with token:', token);
                        captchaToken = token;
                        
                        // Активируем кнопку проверки
                        const button = document.getElementById('verify-button');
                        button.disabled = false;
                        button.classList.add('enabled');
                        document.getElementById('button-text').textContent = '✅ Проверить и участвовать';
                    },
                    'expired-callback': function() {
                        console.log('[CAPTCHA] Turnstile token expired');
                        captchaToken = null;
                        showError('Время проверки истекло. Пожалуйста, пройдите проверку снова.');
                    },
                    'error-callback': function() {
                        console.error('[CAPTCHA] Turnstile error');
                        captchaToken = null;
                        showError('Ошибка проверки. Пожалуйста, попробуйте еще раз.');
                    }
                });
            };
            
            script.onerror = (error) => {
                console.error('[CAPTCHA] Failed to load Turnstile script:', error);
                showError('Не удалось загрузить виджет проверки');
                showTestWidget(); // Fallback к тестовому режиму
            };
            
            document.head.appendChild(script);
        })
        .catch(error => {
            console.error('[CAPTCHA] Error loading config:', error);
            showTestWidget(); // Fallback к тестовому режиму
        });
}

// Показывает тестовый виджет
function showTestWidget() {
    const widgetContainer = document.getElementById('turnstile-widget');
    widgetContainer.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">🛡️</div>
            <div style="color: #a0a0a0; font-size: 14px; margin-bottom: 20px;">
                <b>Тестовый режим проверки безопасности</b><br>
                В реальной системе здесь будет виджет Cloudflare Turnstile.<br>
                Нажмите "Проверить и участвовать" чтобы продолжить.
            </div>
            <button onclick="generateTestToken()" style="
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            ">
                Сгенерировать тестовый токен
            </button>
        </div>
    `;
}

// Генерирует тестовый токен
function generateTestToken() {
    captchaToken = 'test_token_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    console.log('[CAPTCHA] Test token generated:', captchaToken);
    
    // Показываем успех
    document.getElementById('turnstile-widget').innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">✅</div>
            <div style="color: #4CAF50; font-size: 14px;">
                <b>Тестовый токен сгенерирован</b><br>
                Нажмите "Проверить и участвовать" чтобы продолжить.
            </div>
        </div>
    `;
    
    // Активируем кнопку
    const button = document.getElementById('verify-button');
    button.disabled = false;
    button.classList.add('enabled');
    document.getElementById('button-text').textContent = '✅ Проверить и участвовать';
}

// Проверяет Captcha через API
async function verifyCaptcha() {
    console.log('[CAPTCHA] Starting verification and participation');
    
    if (!captchaToken) {
        showError('Пожалуйста, пройдите проверку безопасности');
        return;
    }
    
    if (!userId || !giveawayId) {
        console.error('[CAPTCHA] Missing user_id or giveaway_id');
        showError('Ошибка данных. Пожалуйста, перезагрузите страницу.');
        return;
    }
    
    // Показываем индикатор загрузки
    const button = document.getElementById('verify-button');
    const buttonText = document.getElementById('button-text');
    const buttonLoading = document.getElementById('button-loading');
    
    button.disabled = true;
    buttonText.textContent = 'Проверяем и регистрируем...';
    buttonLoading.style.display = 'inline-block';
    
    // Скрываем предыдущие сообщения
    hideError();
    hideSuccess();
    
    try {
        // Отправляем запрос на проверку Captcha и участие
        console.log('[CAPTCHA] Sending request:', { userId, giveawayId, token: captchaToken.substring(0, 20) + '...' });
        
        const response = await fetch('/api/verify_captcha', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: captchaToken,
                giveaway_id: giveawayId,
                user_id: userId
            })
        });
        
        const data = await response.json();
        console.log('[CAPTCHA] API response:', data);
        
        if (data.ok) {
            console.log('[CAPTCHA] Verification successful:', data.message);
            
            // Показываем успех
            showSuccess();
            
            // Обновляем сообщение успеха
            document.getElementById('success-message').innerHTML = 
                '✅ ' + (data.message || 'Проверка пройдена успешно!');
            
            // 🔥 ЗАКРЫВАЕМ WEBAPP ЧЕРЕЗ TELEGRAM API
            setTimeout(() => {
                const tg = window.Telegram?.WebApp;
                if (tg && typeof tg.close === 'function') {
                    console.log('[CAPTCHA] Closing WebApp');
                    tg.close();
                } else {
                    console.log('[CAPTCHA] Telegram WebApp close not available');
                    // Fallback: редирект на success страницу
                    window.location.href = '/miniapp/success?gid=' + giveawayId;
                }
            }, 2000);
            
        } else {
            console.log('[CAPTCHA] Verification failed:', data.error);
            showError(data.message || data.error || 'Проверка не пройдена. Попробуйте еще раз.');
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
    
    // Прокручиваем к ошибке
    errorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideError() {
    document.getElementById('error-message').style.display = 'none';
}

function showSuccess() {
    const successEl = document.getElementById('success-message');
    successEl.style.display = 'block';
    
    // Прокручиваем к успеху
    successEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideSuccess() {
    document.getElementById('success-message').style.display = 'none';
}

function resetButton() {
    const button = document.getElementById('verify-button');
    const buttonText = document.getElementById('button-text');
    const buttonLoading = document.getElementById('button-loading');
    
    button.disabled = false;
    button.classList.remove('enabled');
    buttonText.textContent = 'Проверить и участвовать';
    buttonLoading.style.display = 'none';
}

function goBack() {
    // Используем Telegram WebApp для навигации
    const tg = window.Telegram?.WebApp;
    if (tg && typeof tg.close === 'function') {
        tg.close();
    } else {
        window.history.back();
    }
}

// Инициализируем страницу при загрузке
document.addEventListener('DOMContentLoaded', initializeCaptchaPage);