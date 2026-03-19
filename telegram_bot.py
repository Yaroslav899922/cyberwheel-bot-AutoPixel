import requests
import sys
import os
import json
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_message(text, url=None, image_url=None):
    """
    Відправляє повідомлення у Telegram.
    ✅ ВИПРАВЛЕНО: повертає True при успіху, False при помилці.
    Без цього auto_parser.py не може знати — записувати URL у базу чи ні.
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Помилка Telegram: TELEGRAM_TOKEN або CHAT_ID не знайдено!")
        return False

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    if image_url and image_url.startswith('http'):
        payload["link_preview_options"] = {
            "is_disabled": False,
            "url": image_url,
            "prefer_large_media": True,
            "show_above_text": True
        }
    else:
        payload["link_preview_options"] = {"is_disabled": True}

    if url:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🌐 Читати оригінал", "url": url}
            ]]
        }
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(endpoint, json=payload, timeout=10)

        if response.status_code != 200 and not payload.get("link_preview_options", {}).get("is_disabled"):
            print(f"🔄 Помилка фото ({response.status_code}). Спроба без прев'ю...")
            payload["link_preview_options"] = {"is_disabled": True}
            response = requests.post(endpoint, json=payload, timeout=10)

        if response.status_code == 200:
            print("📤 [Telegram] Повідомлення успішно відправлено!")
            return True  # ✅ успіх
        else:
            print(f"❌ [Telegram] Помилка. Код: {response.status_code}, Відповідь: {response.text}")
            return False

    except Exception as e:
        print(f"❌ [Telegram] Помилка з'єднання: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        print("❌ ПОМИЛКА: TELEGRAM_TOKEN не знайдено у файлі .env")
    else:
        print("📡 Тестуємо зв'язок з Telegram...")
        result = send_telegram_message("👋 Тест системи.", "https://google.com")
        print(f"Результат: {'✅ Успіх' if result else '❌ Невдача'}")
