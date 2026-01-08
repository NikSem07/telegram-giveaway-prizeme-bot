// SIMPLE TEXT CAPTCHA PAGE LOGIC - ПРОСТАЯ ТЕКСТОВАЯ CAPTCHA

// Глобальные переменные
let captchaToken = null;
let giveawayId = null;
let userId = null;
let captchaDigits = null;
let timerInterval = null;

// Инициализация страницы
async function initializeCaptchaPage() {
    console.log('[SIMPLE-CAPTCHA] Initializing simple text captcha page');
    
    // 1. Получаем данные из Telegram WebApp или sessionStorage
    const tg = window.Telegram?.WebApp;
    
    if (tg) {
        // Используем Telegram WebApp
        tg.expand();
        
        try {
            // Извлекаем user_id из initData
            const initData = tg.initData || '';
            const params = new URLSearchParams(initData);
            const userEncoded = params.get('user');
            
            if (userEncoded) {
                const userJson = decodeURIComponent(userEncoded);
                const user = JSON.parse(userJson);
                userId = user.id;
                console.log(`[SIMPLE-CAPTCHA] User ID from Telegram: ${userId}`);
            }
            
            // Получаем giveaway_id из start_param
            const startParam = tg.initDataUnsafe?.start_param;
            if (startParam && startParam.startsWith('captcha_')) {
                giveawayId = startParam.replace('captcha_', '');
                console.log(`[SIMPLE-CAPTCHA] Giveaway ID from start_param: ${giveawayId}`);
            }
        } catch (error) {
            console.error('[SIMPLE-CAPTCHA] Error parsing Telegram data:', error);
        }
    }
    
    // 2. Fallback: получаем данные из sessionStorage
    if (!giveawayId) {
        giveawayId = sessionStorage.getItem('prizeme_gid');
        console.log(`[SIMPLE-CAPTCHA] Giveaway ID from sessionStorage: ${giveawayId}`);
    }
    
    if (!userId) {
        userId = sessionStorage.getItem('prizeme_user_id');
        console.log(`[SIMPLE-CAPTCHA] User ID from sessionStorage: ${userId}`);
    }
    
    // 3. Проверяем наличие обязательных данных
    if (!giveawayId || !userId) {
        console.error('[SIMPLE-CAPTCHA] Missing required data:', { giveawayId, userId });
        showError('Не удалось определить параметры розыгрыша');
        return;
    }
    
    // 4. Сохраняем данные
    sessionStorage.setItem('prizeme_gid', giveawayId);
    sessionStorage.setItem('prizeme_user_id', userId);
    
    console.log(`[SIMPLE-CAPTCHA] Ready: user_id=${userId}, giveaway_id=${giveawayId}`);
    
    // 5. Загружаем Captcha
    await loadCaptcha();
    
    // 6. Стартуем таймер
    startTimer(60); // 60 секунд
}

// Загружает новую Captcha
async function loadCaptcha() {
    console.log('[SIMPLE-CAPTCHA] Loading new captcha');
    
    try {
        // Показываем индикатор загрузки
        document.getElementById('captcha-digits').innerHTML = '<div class="captcha-loading-small"></div>';
        document.getElementById('captcha-input').value = '';
        document.getElementById('captcha-input').disabled = true;
        
        // 🔥 В РЕАЛЬНОЙ СИТУАЦИИ: здесь был бы запрос к боту для генерации Captcha
        // 🔥 НО для тестирования: генерируем случайные 4 цифры
        
        // Генерируем случайные 4 цифры
        captchaDigits = generateRandomDigits(4);
        captchaToken = 'token_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        console.log(`[SIMPLE-CAPTCHA] Generated digits: ${captchaDigits}, token: ${captchaToken.substring(0, 20)}...`);
        
        // Отображаем цифры
        displayCaptchaDigits(captchaDigits);
        
        // Активируем поле ввода
        document.getElementById('captcha-input').disabled = false;
        document.getElementById('captcha-input').focus();
        
        // Сбрасываем кнопку
        resetButton();
        
    } catch (error) {
        console.error('[SIMPLE-CAPTCHA] Error loading captcha:', error);
        showError('Не удалось загрузить проверку');
        
        // Fallback: показываем тестовые цифры
        captchaDigits = '1234';
        displayCaptchaDigits(captchaDigits);
    }
}

// Генерирует случайные цифры
function generateRandomDigits(length) {
    let result = '';
    for (let i = 0; i < length; i++) {
        result += Math.floor(Math.random() * 10);
    }
    return result;
}

// Отображает цифры Captcha
function displayCaptchaDigits(digits) {
    const container = document.getElementById('captcha-digits');
    container.innerHTML = '';
    
    for (let i = 0; i < digits.length; i++) {
        const digitSpan = document.createElement('span');
        digitSpan.className = 'captcha-digit';
        digitSpan.textContent = digits[i];
        container.appendChild(digitSpan);
    }
}

// Запускает таймер
function startTimer(seconds) {
    clearInterval(timerInterval);
    
    let timeLeft = seconds;
    const timerElement = document.getElementById('timer-seconds');
    
    timerElement.textContent = timeLeft;
    
    timerInterval = setInterval(() => {
        timeLeft--;
        timerElement.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            showError('Время проверки истекло. Пожалуйста, обновите цифры.');
            document.getElementById('verify-button').disabled = true;
        } else if (timeLeft <= 10) {
            // Меняем цвет при малом времени
            document.getElementById('captcha-timer').style.color = '#ff6b6b';
        }
    }, 1000);
}

// Проверяет Captcha через API
async function verifyCaptcha() {
    console.log('[SIMPLE-CAPTCHA] Starting verification');
    
    // Получаем введенные цифры
    const userInput = document.getElementById('captcha-input').value.trim();
    
    // Валидация ввода
    if (!userInput || userInput.length !== 4 || !/^\d{4}$/.test(userInput)) {
        showError('Пожалуйста, введите ровно 4 цифры');
        return;
    }
    
    if (!captchaToken || !giveawayId || !userId) {
        showError('Ошибка данных. Пожалуйста, обновите страницу.');
        return;
    }
    
    console.log(`[SIMPLE-CAPTCHA] Verification: input=${userInput}, expected=${captchaDigits}`);
    
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
        // 🔥 ОТПРАВЛЯЕМ ЗАПРОС НА ПРОВЕРКУ В NODE.JS API
        console.log('[SIMPLE-CAPTCHA] Sending to API:', { 
            giveaway_id: giveawayId, 
            user_id: userId,
            token: captchaToken,
            answer: userInput
        });
        
        const response = await fetch('/api/verify_captcha', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: captchaToken,
                giveaway_id: parseInt(giveawayId),
                user_id: parseInt(userId),
                answer: userInput
            })
        });
        
        const data = await response.json();
        console.log('[SIMPLE-CAPTCHA] API response:', data);
        
        if (data.ok) {
            console.log('[SIMPLE-CAPTCHA] Verification successful:', data.message);
            
            // Показываем успех
            showSuccess();
            document.getElementById('success-message').innerHTML = 
                '✅ ' + (data.message || 'Проверка пройдена успешно!');
            
            // 🔥 ЗАКРЫВАЕМ WEBAPP ИЛИ РЕДИРЕКТИМ
            setTimeout(() => {
                const tg = window.Telegram?.WebApp;
                if (tg && typeof tg.close === 'function') {
                    console.log('[SIMPLE-CAPTCHA] Closing WebApp');
                    tg.close();
                } else {
                    console.log('[SIMPLE-CAPTCHA] Telegram WebApp close not available');
                    // Fallback: редирект на success страницу
                    window.location.href = '/miniapp/success?gid=' + giveawayId;
                }
            }, 2000);
            
        } else {
            console.log('[SIMPLE-CAPTCHA] Verification failed:', data.error);
            showError(data.message || data.error || 'Неверные цифры. Попробуйте еще раз.');
            
            // Сбрасываем кнопку и очищаем поле
            resetButton();
            document.getElementById('captcha-input').value = '';
            document.getElementById('captcha-input').focus();
        }
        
    } catch (error) {
        console.error('[SIMPLE-CAPTCHA] Verification error:', error);
        showError('Ошибка при проверке. Попробуйте еще раз.');
        resetButton();
    }
}

// Обновляет Captcha
function refreshCaptcha() {
    console.log('[SIMPLE-CAPTCHA] Refreshing captcha');
    loadCaptcha();
    startTimer(60); // Сбрасываем таймер
    hideError();
}

// Навигация назад
function goBack() {
    const tg = window.Telegram?.WebApp;
    if (tg && typeof tg.close === 'function') {
        tg.close();
    } else {
        window.history.back();
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
    buttonText.textContent = 'Проверить';
    buttonLoading.style.display = 'none';
}

// Инициализируем страницу при загрузке
document.addEventListener('DOMContentLoaded', initializeCaptchaPage);