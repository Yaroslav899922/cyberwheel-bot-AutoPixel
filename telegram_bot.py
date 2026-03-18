import requests
import sys
import os
import json # ДОДАНО: потрібно для формування кнопки
from dotenv import load_dotenv # Додано для роботи з .env

# Завантажуємо змінні з файлу .env (якщо він є локально)
load_dotenv()

# Налаштування для виводу емодзі у Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

# Тепер дані беруться або з .env (локально), або з Environment Variables (Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ЗМІНЕНО: Тепер функція приймає text, url (посилання) та image_url (фото)
def send_telegram_message(text, url=None, image_url=None):
    """Відправляє фото з текстом або звичайне повідомлення у ваш Telegram з кнопкою"""
    
    # Перевірка, чи завантажились ключі
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Помилка Telegram: TELEGRAM_TOKEN або CHAT_ID не знайдено!")
        return

    # ХІРУРГІЧНА ПРАВКА: Логіка відправки великого ФОТО
    # Якщо є картинка і текст влазить у ліміт підпису Telegram (1024 символи)
    if image_url and image_url.startswith('http') and len(text) <= 1024:
        endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": text,
            "parse_mode": "HTML"
        }
    else:
        # Якщо фото немає або текст задовгий — шлемо просто текст
        endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True # ЖОРСТКО ВИМИКАЄМО прев'ю, щоб не ліз Facebook
        }
    
    # ДОДАНО: Якщо передано посилання — створюємо кнопку
    if url:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🌐 Читати оригінал", "url": url}
            ]]
        }
        payload["reply_markup"] = reply_markup # Передаємо словник, json=payload сам його конвертує
    
    try:
        response = requests.post(endpoint, json=payload, timeout=15)
        
        # Запобіжник: якщо фото "бите" і Telegram його відхилив, пробуємо відправити як текст
        if response.status_code != 200 and "sendPhoto" in endpoint:
            print(f"🔄 Помилка фото ({response.status_code}). Спроба відправити як текст...")
            endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload.pop("photo", None)
            payload["text"] = payload.pop("caption")
            payload["disable_web_page_preview"] = True
            response = requests.post(endpoint, json=payload, timeout=15)

        if response.status_code == 200:
            print("📤[Telegram] Повідомлення успішно відправлено!")
        else:
            print(f"❌[Telegram] Помилка. Код: {response.status_code}, Відповідь: {response.text}")
    except Exception as e:
        print(f"❌ [Telegram] Помилка з'єднання: {e}")

if __name__ == "__main__":
    # Тест для перевірки підключення
    if not TELEGRAM_TOKEN:
        print("❌ ПОМИЛКА: TELEGRAM_TOKEN не знайдено у файлі .env")
    else:
        print("📡 Тестуємо зв'язок з Telegram...")
        test_msg = "👋 Привіт! Це тест системи безпеки з використанням .env файлу."
        send_telegram_message(test_msg, "https://google.com")
