import os
import requests
import re

# Завантажуємо ключі з середовища
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")

# Версія Graph API — винесено в одне місце.
# ⚠️ Перевір актуальну версію на developers.facebook.com, коли отримуватимеш токен.
FB_API_VERSION = "v19.0"


def send_facebook_post(message, image_url=None, source_url=None):
    """
    Відправляє текст та (опціонально) зображення на сторінку Facebook.
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ Facebook API ключі не знайдено. Пропускаємо публікацію у FB.")
        return False

    # 1. Обробляємо blockquote (Вердикт Софії) ДО очищення — обрамляємо лініями
    clean_message = re.sub(
        r'<blockquote[^>]*>(.*?)</blockquote>',
        r'\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\1\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️',
        message, flags=re.DOTALL
    )

    # 2. Знімаємо всі інші HTML-теги (<b>, <i>, <a> тощо)
    clean_message = re.sub(r'<[^>]+>', '', clean_message)

    # 3. Прибираємо хвіст із соцмережами (у FB-пості він без посилань — лише сміття)
    #    Блок соцмереж починається з рядка про Instagram.
    clean_message = re.split(r'\n+📷\s*Instagram', clean_message)[0].strip()

    # 4. Прибираємо рядок "Читати повністю →" — поставимо URL прямо в кінці
    if source_url:
        clean_message = clean_message.replace("Читати повністю →", "").strip()
        clean_message += f"\n\n🔗 {source_url}"

    try:
        if image_url:
            # Якщо є картинка — публікуємо фото з підписом
            url = f"https://graph.facebook.com/{FB_API_VERSION}/{FB_PAGE_ID}/photos"
            payload = {
                "url": image_url,
                "caption": clean_message,
                "access_token": FB_ACCESS_TOKEN
            }
        else:
            # Якщо картинки немає — публікуємо просто текстовий статус
            url = f"https://graph.facebook.com/{FB_API_VERSION}/{FB_PAGE_ID}/feed"
            payload = {
                "message": clean_message,
                "access_token": FB_ACCESS_TOKEN
            }

        response = requests.post(url, data=payload, timeout=15)

        try:
            result = response.json()
        except ValueError:
            print(f"❌ FB Помилка: сервер повернув не-JSON (код {response.status_code})")
            return False

        if response.status_code == 200 and not result.get("error"):
            print("✅ FB: Успішно опубліковано на сторінці Facebook!")
            return True
        else:
            print(f"❌ FB Помилка: {result}")
            return False

    except Exception as e:
        print(f"❌ FB Критична помилка: {type(e).__name__}: {e}")
        return False
