// SIMPLE TEXT CAPTCHA PAGE LOGIC - ПРОСТАЯ ТЕКСТОВАЯ CAPTCHA

// Глобальные переменные
let captchaToken = null;
let giveawayId = null;
let userId = null;
let captchaDigits = null;
let timerInterval = null;

// Функция для парсинга start_param
function parseStartParam(startParam) {
    console.log(`[SIMPLE-CAPTCHA] Parsing start_param: ${startParam}`);
    
    if (!startParam || !startParam.startsWith('captcha_')) {
        console.error('[SIMPLE-CAPTCHA] Invalid start_param format');
        return null;
    }
    
    // Формат: captcha_{gid}_{user_id}_{digits}_{token}
    // Пример: captcha_218_428883823_1234_abc123def456
    
    const parts = startParam.split('_');
    
    if (parts.length < 5) {
        console.error('[SIMPLE-CAPTCHA] Invalid start_param parts:', parts);
        return null;
    }
    
    // parts[0] = "captcha"
    // parts[1] = giveaway_id
    // parts[2] = user_id
    // parts[3] = captcha_digits (должно быть 4 цифры)
    // parts[4+] = captcha_token (может содержать дополнительные подчеркивания)
    
    const giveawayId = parts[1];
    const userId = parts[2];
    const captchaDigits = parts[3];
    
    // Проверяем что digits - это 4 цифры
    if (!/^\d{4}$/.test(captchaDigits)) {
        console.error('[SIMPLE-CAPTCHA] Invalid captcha digits format:', captchaDigits);
        return null;
    }
    
    // Токен может содержать дополнительные подчеркивания, соединяем все оставшиеся части
    const captchaToken = parts.slice(4).join('_');
    
    // Проверяем что токен не пустой
    if (!captchaToken || captchaToken.length < 10) {
        console.error('[SIMPLE-CAPTCHA] Invalid captcha token:', captchaToken);
        return null;
    }
    
    console.log(`[SIMPLE-CAPTCHA] Successfully parsed:`, {
        giveawayId,
        userId,
        captchaDigits,
        captchaTokenLength: captchaToken.length
    });
    
    return {
        giveawayId,
        userId,
        captchaDigits,
        captchaToken
    };
}

// Инициализация страницы
async function initializeCaptchaPage() {
    console.log('[SIMPLE-CAPTCHA] Initializing simple text captcha page');
    
    // 1. Получаем данные из Telegram WebApp
    const tg = window.Telegram?.WebApp;
    
    if (tg) {
        // Используем Telegram WebApp
        tg.expand();
    }
    
    // 2. Получаем данные из start_param (ПРАВИЛЬНЫЙ ПАРСИНГ)
    let startParam = null;
    
    // 2.1. Пробуем получить из Telegram WebApp initData
    if (tg && tg.initDataUnsafe?.start_param) {
        startParam = tg.initDataUnsafe.start_param;
        console.log(`[SIMPLE-CAPTCHA] start_param from Telegram initData: ${startParam}`);
    }
    
    // 2.2. Пробуем получить из URL параметров (fallback)
    if (!startParam) {
        try {
            const url = new URL(window.location.href);
            startParam = url.searchParams.get('tgWebAppStartParam');
            console.log(`[SIMPLE-CAPTCHA] start_param from URL: ${startParam}`);
        } catch (error) {
            console.error('[SIMPLE-CAPTCHA] Error parsing URL:', error);
        }
    }

    let gidFromUrl = null;
    try {
        const url = new URL(window.location.href);
        gidFromUrl = url.searchParams.get('gid');
        if (gidFromUrl) {
            console.log(`[SIMPLE-CAPTCHA] gid from URL: ${gidFromUrl}`);
        }
    } catch (e) {}

    // 3. Парсим start_param если он есть и имеет правильный формат
    if (startParam && startParam.startsWith('captcha_')) {
        const parsed = parseStartParam(startParam);
        if (parsed) {
            giveawayId = parsed.giveawayId;
            userId = parsed.userId;
            captchaDigits = parsed.captchaDigits;
            captchaToken = parsed.captchaToken;
            
            console.log(`[SIMPLE-CAPTCHA] Parsed from start_param:`, {
                giveawayId,
                userId,
                captchaDigits: captchaDigits ? `${captchaDigits.substring(0, 2)}...` : 'null',
                captchaToken: captchaToken ? `${captchaToken.substring(0, 10)}...` : 'null'
            });
        } else {
            console.error('[SIMPLE-CAPTCHA] Failed to parse start_param:', startParam);
        }
    } else if (startParam) {
        console.warn(`[SIMPLE-CAPTCHA] Invalid start_param format: ${startParam}`);
    }
    
    // 4. Fallback: получаем данные из sessionStorage (если start_param не сработал)
    if (!giveawayId) {
        giveawayId = sessionStorage.getItem('prizeme_gid');
        console.log(`[SIMPLE-CAPTCHA] Giveaway ID from sessionStorage: ${giveawayId}`);
    }
    
    if (!userId && tg?.initDataUnsafe?.user?.id) {
        userId = String(tg.initDataUnsafe.user.id);
        console.log(`[SIMPLE-CAPTCHA] User ID from initDataUnsafe: ${userId}`);
    }
    
    // Fallback: пробуем достать userId из сохраненного init_data
    if (!userId) {
        try {
            const storedInit = sessionStorage.getItem('prizeme_init_data') || '';
            if (storedInit) {
                const params = new URLSearchParams(storedInit);
                const userEncoded = params.get('user');
                if (userEncoded) {
                    const user = JSON.parse(decodeURIComponent(userEncoded));
                    if (user?.id) {
                        userId = String(user.id);
                        console.log(`[SIMPLE-CAPTCHA] User ID from sessionStorage.prizeme_init_data: ${userId}`);
                    }
                }
            }
        } catch (e) {
            console.error('[SIMPLE-CAPTCHA] Error parsing prizeme_init_data:', e);
        }
    }

    if (!userId) {
        userId = sessionStorage.getItem('prizeme_user_id');
        console.log(`[SIMPLE-CAPTCHA] User ID from sessionStorage: ${userId}`);
    }
    
    if (!giveawayId && gidFromUrl) {
        giveawayId = gidFromUrl;
    }

    // 5. Проверяем наличие обязательных данных
    if (!giveawayId || !userId) {
        console.error('[SIMPLE-CAPTCHA] Missing required data:', { giveawayId, userId });
        showError('Не удалось определить параметры розыгрыша');
        return;
    }
    
    // 6. Сохраняем данные в sessionStorage для резерва
    sessionStorage.setItem('prizeme_gid', giveawayId);
    sessionStorage.setItem('prizeme_user_id', userId);
    
    console.log(`[SIMPLE-CAPTCHA] Ready: user_id=${userId}, giveaway_id=${giveawayId}`);
    
    // Если digits/token не пришли из start_param — создаем captcha-сессию через backend
    if (!captchaDigits || !captchaToken) {
        console.log("[SIMPLE-CAPTCHA] No captcha data in start_param, creating session via API...");

        const resp = await fetch("/api/create_captcha_session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                giveaway_id: parseInt(giveawayId, 10),
                user_id: parseInt(userId, 10),
            }),
        });

        const data = await resp.json().catch(() => ({}));

        if (!resp.ok || !data.ok) {
            console.error("[SIMPLE-CAPTCHA] Failed to create captcha session:", data);
            showError(data.message || "Не удалось создать проверку. Попробуйте еще раз.");
            return;
        }

        captchaDigits = data.digits;
        captchaToken = data.token;

        console.log("[SIMPLE-CAPTCHA] Captcha session created:", {
            giveawayId, userId, captchaDigits, tokenLen: captchaToken?.length
        });
    }

    // 7. Загружаем Captcha (будет использовать переданные цифры из start_param)
    await loadCaptcha();
    
    // 8. Стартуем таймер
    startTimer(60); // 60 секунд
    
    // 9. Фокус на поле ввода
    setTimeout(() => {
        const input = document.getElementById('captcha-input');
        if (input) {
            input.focus();
        }
    }, 500);
}

// Загружает Captcha (использует переданные цифры или генерирует тестовые)
async function loadCaptcha() {
    console.log('[SIMPLE-CAPTCHA] Loading captcha');
    
    try {
        // Показываем индикатор загрузки
        document.getElementById('captcha-digits').innerHTML = '<div class="captcha-loading-small"></div>';
        document.getElementById('captcha-input').value = '';
        document.getElementById('captcha-input').disabled = true;
        
        // 🔥 ЕСЛИ УЖЕ ЕСТЬ ЦИФРЫ ИЗ start_param - ИСПОЛЬЗУЕМ ИХ
        if (captchaDigits && captchaToken) {
            console.log(`[SIMPLE-CAPTCHA] Using provided digits: ${captchaDigits}`);
        } else {
            // 🔥 FALLBACK: генерируем тестовые цифры (для отладки)
            console.warn('[SIMPLE-CAPTCHA] No captcha data provided, using test mode');
            captchaDigits = generateRandomDigits(4);
            captchaToken = 'test_token_' + Date.now();
            
            // Записываем в sessionStorage для тестирования
            sessionStorage.setItem('test_captcha_digits', captchaDigits);
            sessionStorage.setItem('test_captcha_token', captchaToken);
        }
        
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

// Проверяем Captcha через API
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
    console.log(`[SIMPLE-CAPTCHA] Sending to API:`, { 
        giveaway_id: giveawayId, 
        user_id: userId,
        token: captchaToken,
        answer: userInput
    });
    
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
            
            showSuccess();
            document.getElementById('success-message').innerHTML = '✅ ' + (data.message || 'Проверка пройдена успешно!');

            // Показываем успех
            // Подготовим данные для success/already экранов (они читают prizeme_ticket и prizeme_end_at)
            try {
                sessionStorage.setItem('prizeme_ticket', data.ticket_code || '');  // ✅ ключ как в app.js
                sessionStorage.setItem('prizeme_gid', giveawayId || '');

                // Достаём end_at_utc через /api/check (как в обычном флоу)
                const tg = window.Telegram?.WebApp;
                let init_data = tg?.initData || '';

                if (!init_data) {
                    const storedInit = sessionStorage.getItem('prizeme_init_data');
                    if (storedInit) init_data = storedInit;
                }

                if (init_data) {
                    const resp = await fetch('/api/check', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            gid: parseInt(giveawayId, 10),
                            init_data: init_data
                        })
                    });

                    const checkData = await resp.json().catch(() => ({}));
                    if (resp.ok && checkData && checkData.end_at_utc) {
                        sessionStorage.setItem('prizeme_end_at', checkData.end_at_utc); // ✅ ключ как в app.js
                    }
                }
            } catch (e) {
                console.error('[SIMPLE-CAPTCHA] Failed to prepare success/already storage:', e);
            }

            // ✅ Редирект на нужную статическую страницу
            const ticket = encodeURIComponent(data.ticket_code || '');
            const gid = encodeURIComponent(giveawayId || '');

            if (data.already_participating) {
                window.location.href = `/miniapp/already_participating.html?gid=${gid}&ticket_code=${ticket}`;
            } else {
                window.location.href = `/miniapp/success.html?gid=${gid}&ticket_code=${ticket}`;
            }

            
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
async function refreshCaptcha() {
    console.log('[SIMPLE-CAPTCHA] Refreshing captcha');

    hideError();

    if (!giveawayId || !userId) {
        showError('Ошибка данных. Обновите страницу.');
        return;
    }

    try {
        const resp = await fetch('/api/create_captcha_session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                giveaway_id: parseInt(giveawayId, 10),
                user_id: parseInt(userId, 10)
            })
        });

        const data = await resp.json().catch(() => ({}));
        console.log('[SIMPLE-CAPTCHA] Refresh API response:', data);

        if (!resp.ok || !data.ok) {
            showError(data.message || 'Не удалось обновить цифры. Попробуйте ещё раз.');
            return;
        }

        // ✅ обновляем глобальные значения
        captchaDigits = data.digits;
        captchaToken = data.token;

        // ✅ сохраняем, чтобы не терялось при перезагрузках
        sessionStorage.setItem('captchaDigits', captchaDigits);
        sessionStorage.setItem('captchaToken', captchaToken);

        // ✅ обновляем UI
        loadCaptcha();
        startTimer(60);

        // очищаем поле ввода
        const input = document.getElementById('captcha-input');
        if (input) {
            input.value = '';
            input.focus();
        }
    } catch (e) {
        console.error('[SIMPLE-CAPTCHA] Refresh error:', e);
        showError('Ошибка сети при обновлении. Попробуйте ещё раз.');
    }
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