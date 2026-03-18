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

# ЗМІНЕНО: Тепер функція приймає text та url (посилання)
def send_telegram_message(text, url=None, image_url=None):
    """Відправляє текстове повідомлення у ваш Telegram з кнопкою"""
    
    # Перевірка, чи завантажились ключі
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Помилка Telegram: TELEGRAM_TOKEN або CHAT_ID не знайдено!")
        return

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML" # Дозволяє жирний шрифт та курсив
    }

    # ХІРУРГІЧНА ПРАВКА: Сучасна робота з великими фото (обходимо ліміт 1024 символи)
    if image_url and image_url.startswith('http'):
        # Примусово малюємо велике фото над текстом. ФБ та Інста будуть ігноруватися!
        payload["link_preview_options"] = {
            "is_disabled": False,
            "url": image_url,
            "prefer_large_media": True,
            "show_above_text": True
        }
    else:
        # Якщо фото немає — повністю вимикаємо прев'ю
        payload["link_preview_options"] = {
            "is_disabled": True
        }
    
    # ДОДАНО: Якщо передано посилання — створюємо кнопку
    if url:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🌐 Читати оригінал", "url": url}
            ]]
        }
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(endpoint, json=payload, timeout=10)
        
        # Запобіжник: якщо картинка бита, Телеграм видасть помилку. Тоді шлемо просто текст.
        if response.status_code != 200 and not payload.get("link_preview_options", {}).get("is_disabled"):
            print(f"🔄 Помилка фото ({response.status_code}). Спроба відправити без прев'ю...")
            payload["link_preview_options"] = {"is_disabled": True}
            response = requests.post(endpoint, json=payload, timeout=10)

        if response.status_code == 200:
            print("📤 [Telegram] Повідомлення успішно відправлено!")
        else:
            print(f"❌ [Telegram] Помилка. Код: {response.status_code}, Відповідь: {response.text}")
    except Exception as e:
        print(f"❌[Telegram] Помилка з'єднання: {e}")

if __name__ == "__main__":
    # Тест для перевірки підключення
    if not TELEGRAM_TOKEN:
        print("❌ ПОМИЛКА: TELEGRAM_TOKEN не знайдено у файлі .env")
    else:
        print("📡 Тестуємо зв'язок з Telegram...")
        test_msg = "👋 Привіт! Це тест системи безпеки з використанням .env файлу."
        send_telegram_message(test_msg, "https://google.com")
