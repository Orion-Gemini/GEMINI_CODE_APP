class GeminiApp {
    constructor() {
        this.tg = window.Telegram.WebApp;
        this.backendUrl = 'https://your-server.com/api'; // Ваш сервер
        this.userId = this.tg.initDataUnsafe.user?.id;
        this.currentFile = null;

        this.init();
    }

    init() {
        this.tg.expand();
        this.tg.enableClosingConfirmation();
        this.bindEvents();
        this.loadHistory();
    }

    bindEvents() {
        document.getElementById('sendBtn').addEventListener('click', () => this.sendMessage());
        document.getElementById('messageInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        document.getElementById('uploadBtn').addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });

        document.getElementById('fileInput').addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });

        document.getElementById('resetBtn').addEventListener('click', () => {
            this.resetHistory();
        });
    }

    async sendMessage() {
        const input = document.getElementById('messageInput');
        const message = input.value.trim();

        if (!message && !this.currentFile) return;

        this.addMessage(message, 'user');
        input.value = '';

        const loadingId = this.addMessage('Думаю...', 'bot', true);

        try {
            let response;

            if (this.currentFile) {
                response = await this.sendFileWithMessage(message);
                this.currentFile = null;
                document.getElementById('fileName').textContent = '';
            } else {
                response = await this.sendTextMessage(message);
            }

            this.updateMessage(loadingId, response);
        } catch (error) {
            this.updateMessage(loadingId, `❌ Ошибка: ${error.message}`);
        }
    }

    async sendTextMessage(message) {
        const response = await fetch(`${this.backendUrl}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: this.userId,
                message: message
            })
        });

        if (!response.ok) throw new Error('Network error');
        const data = await response.json();
        return data.response;
    }

    async sendFileWithMessage(message) {
        const reader = new FileReader();

        return new Promise((resolve, reject) => {
            reader.onload = async (e) => {
                try {
                    const base64 = e.target.result.split(',')[1];
                    const response = await fetch(`${this.backendUrl}/upload`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_id: this.userId,
                            file_data: base64,
                            mime_type: this.currentFile.type,
                            prompt: message || 'Опиши этот файл'
                        })
                    });

                    if (!response.ok) throw new Error('Upload failed');
                    const data = await response.json();
                    resolve(data.response);
                } catch (error) {
                    reject(error);
                }
            };

            reader.readAsDataURL(this.currentFile);
        });
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Проверяем тип файла
        const validTypes = ['image/jpeg', 'image/png', 'application/pdf', 'text/plain'];
        if (!validTypes.includes(file.type)) {
            alert('Поддерживаются только JPG, PNG, PDF и TXT файлы');
            return;
        }

        this.currentFile = file;
        document.getElementById('fileName').textContent = file.name;
    }

    addMessage(text, sender, isLoading = false) {
        const messages = document.getElementById('messages');
        const messageDiv = document.createElement('div');
        const messageId = 'msg_' + Date.now();

        messageDiv.id = messageId;
        messageDiv.className = `message ${sender} ${isLoading ? 'loading' : ''}`;
        messageDiv.innerHTML = this.formatMessage(text);

        messages.appendChild(messageDiv);
        messages.scrollTop = messages.scrollHeight;

        return messageId;
    }

    updateMessage(messageId, newText) {
        const messageDiv = document.getElementById(messageId);
        if (messageDiv) {
            messageDiv.className = 'message bot';
            messageDiv.innerHTML = this.formatMessage(newText);
        }
    }

    formatMessage(text) {
        // Простое форматирование Markdown
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    async resetHistory() {
        try {
            await fetch(`${this.backendUrl}/reset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: this.userId })
            });

            document.getElementById('messages').innerHTML = '';
            this.tg.showPopup({
                title: 'Успех',
                message: 'История очищена',
                buttons: [{ type: 'ok' }]
            });
        } catch (error) {
            this.tg.showPopup({
                title: 'Ошибка',
                message: 'Не удалось очистить историю',
                buttons: [{ type: 'ok' }]
            });
        }
    }

    loadHistory() {
        // Можно добавить загрузку истории при старте
        this.addMessage(
            '👋 Привет! Я Gemini AI помощник. Задавайте вопросы или загружайте файлы для анализа.',
            'bot'
        );
    }
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    new GeminiApp();
});