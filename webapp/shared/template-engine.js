// webapp/shared/template-engine.js
const TemplateEngine = {
    // Рендер шаблона с контекстом
    render(templateFn, context = {}) {
        return templateFn(context);
    },
    
    // Создание HTML элемента из строки
    createElement(htmlString) {
        const template = document.createElement('template');
        template.innerHTML = htmlString.trim();
        return template.content.firstChild;
    },
    
    // Безопасная вставка HTML
    safeHtml(strings, ...values) {
        return strings.reduce((result, str, i) => {
            const value = values[i] || '';
            return result + str + this.escapeHtml(value);
        }, '');
    },
    
    // Экранирование HTML (защита от XSS)
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

export default TemplateEngine;
