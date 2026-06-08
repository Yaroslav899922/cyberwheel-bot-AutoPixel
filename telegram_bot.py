import requests
import sys
import os
import json
import mimetypes
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def _redact_telegram_token(value):
    """Не дозволяє випадково вивести TELEGRAM_TOKEN у логи."""
    text = str(value)
    if TELEGRAM_TOKEN:
        text = text.replace(TELEGRAM_TOKEN, "***TELEGRAM_TOKEN***")
    return text


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
            return True
        else:
            print(f"❌ [Telegram] Помилка. Код: {response.status_code}, Відповідь: {_redact_telegram_token(response.text)}")
            return False

    except Exception as e:
        print(f"❌ [Telegram] Помилка з'єднання: {type(e).__name__}: {_redact_telegram_token(e)}")
        return False


def send_telegram_video(video_path, caption=None, parse_mode=None):
    """
    Відправляє локальний MP4/MOV/WebM-файл у Telegram як відео.

    Використовується для MVP Reels: бот генерує ролик і надсилає його
    у Telegram на ручну перевірку. Функція НЕ публікує відео у Facebook
    і НЕ змінює логіку основного парсера.

    Args:
        video_path: шлях до локального відеофайлу.
        caption: необов'язковий підпис до відео. Telegram має ліміт
            1024 символи для caption, тому довгий текст обрізається.
        parse_mode: можна передати "HTML", якщо caption уже безпечний HTML.
            За замовчуванням None, щоб не ламати відправку через випадкові теги.

    Returns:
        True при успішній відправці, False при помилці.
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Помилка Telegram Video: TELEGRAM_TOKEN або CHAT_ID не знайдено!")
        return False

    path = Path(video_path)
    if not path.exists() or not path.is_file():
        print(f"❌ [Telegram Video] Файл не знайдено: {path}")
        return False

    if path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        print(f"❌ [Telegram Video] Непідтримуваний формат відео: {path.suffix}")
        return False

    max_video_bytes = 49 * 1024 * 1024
    file_size = path.stat().st_size
    if file_size > max_video_bytes:
        print(f"❌ [Telegram Video] Файл завеликий для безпечного upload: {file_size / 1024 / 1024:.1f} MB")
        return False

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo"

    payload = {
        "chat_id": CHAT_ID,
        "supports_streaming": "true",
    }

    if caption:
        safe_caption = str(caption).strip()
        if len(safe_caption) > 1000:
            safe_caption = safe_caption[:997].rstrip() + "..."
        payload["caption"] = safe_caption

    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        with path.open("rb") as video_file:
            mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
            files = {"video": (path.name, video_file, mime_type)}
            response = requests.post(endpoint, data=payload, files=files, timeout=90)

        if response.status_code == 200:
            print("📤 [Telegram Video] Відео успішно відправлено!")
            return True

        print(f"❌ [Telegram Video] Помилка. Код: {response.status_code}, Відповідь: {_redact_telegram_token(response.text)}")
        return False

    except Exception as e:
        print(f"❌ [Telegram Video] Помилка з'єднання: {type(e).__name__}: {_redact_telegram_token(e)}")
        return False


if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        print("❌ ПОМИЛКА: TELEGRAM_TOKEN не знайдено у файлі .env")
    else:
        print("📡 Тестуємо зв'язок з Telegram...")
        result = send_telegram_message("👋 Тест системи.", "https://google.com")
        print(f"Результат: {'✅ Успіх' if result else '❌ Невдача'}")
