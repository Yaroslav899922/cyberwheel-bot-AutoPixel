import requests
import sys
import os # Додано для безпечної роботи з ключами

# Налаштування для виводу емодзі у Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

# ТЕПЕР МИ НЕ ПИШЕМО ДАНІ ТУТ ПРЯМИМ ТЕКСТОМ
# Коли ми перейдемо на Render, ми вкажемо ці значення у налаштуваннях
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_message(text):
    """Відправляє текстове повідомлення у ваш Telegram"""
    
    # Перевірка на випадок, якщо ключі не завантажились
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Помилка: TELEGRAM_TOKEN або CHAT_ID не встановлені в Environment Variables!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown" # Дозволяє використовувати жирний шрифт та курсив
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📤 [Telegram] Повідомлення успішно відправлено!")
        else:
            print(f"❌ [Telegram] Помилка відправки. Код: {response.status_code}, Відповідь: {response.text}")
    except Exception as e:
        print(f"❌ [Telegram] Помилка з'єднання: {e}")

if __name__ == "__main__":
    # Тестове повідомлення при прямому запуску цього файлу
    test_msg = "👋 Привіт! Це тестове повідомлення від вашого AI-Парсера."
    send_telegram_message(test_msg)