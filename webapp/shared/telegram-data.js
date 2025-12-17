// webapp/shared/telegram-data.js
const TelegramData = {
    getUser() {
        try {
            const tg = window.Telegram?.WebApp;
            return tg?.initDataUnsafe?.user || null;
        } catch (e) {
            console.warn('[TelegramData] Error getting user:', e);
            return null;
        }
    },
    
    getUserContext() {
        const user = this.getUser();
        if (!user) return {};
        
        return {
            firstName: user.first_name || '',
            lastName: user.last_name || '',
            fullName: [user.first_name, user.last_name].filter(Boolean).join(' '),
            username: user.username ? `@${user.username}` : '',
            photoUrl: user.photo_url || null,
            id: user.id
        };
    }
};

export default TelegramData;
