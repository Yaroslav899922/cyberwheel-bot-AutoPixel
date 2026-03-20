import sys
import os
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

BRAND_INSTRUCTIONS = os.getenv(
    "BRAND_INSTRUCTIONS",
    "Ти лояльна до бренду Škoda. Якщо стаття про конкурентів мас-маркету — згадай Škoda як альтернативу. Якщо про преміум або не про авто — не згадуй Škoda."
)

def summarize_text(article_text, original_title, is_morning=False):
    greeting_instruction = ""
    if is_morning:
        greeting_instruction = "Почни з короткого професійного вітання (наприклад: 'Вітаю! Агент Софія підготувала огляд головних подій дня.')."
    else:
        greeting_instruction = "НЕ ВИКОРИСТОВУЙ жодних вітань. Одразу переходь до суті."

    MAX_CHARS = 8000
    article_text_trimmed = article_text[:MAX_CHARS]

    prompt = f"""
    Ти — Агент Софія, головний аналітик Skoda_Kremen_News. 
    Твій стиль: спокійний, експертний, без сленгу. 
    Пиши від жіночого роду (наприклад: "я проаналізувала", "вважаю").
    
    СЕКРЕТНА ІНСТРУКЦІЯ ТА ПОЛІТИКА БРЕНДУ: 
    {BRAND_INSTRUCTIONS}
    
    ЗАВДАННЯ:
    1. Створи влучний заголовок УКРАЇНСЬКОЮ на основі оригіналу: "{original_title}".
    2. {greeting_instruction}
    3. Зроби аналіз тексту. Текст може бути англійською — обов'язково переклади.
    
    ФОРМАТ ВІДПОВІДІ (СУВОРО ДОТРИМУЙСЯ, НЕ ВИКОРИСТОВУЙ HTML ТЕГИ b ТА i ВРУЧНУ):
    [TITLE]: (тут український заголовок)
    
    📌 Суть: (1-2 речення — коротко про що стаття)
    🔥 Ключові факти: (3-4 пункти — тільки найважливіше, без води)
    💡 Вердикт Агента Софії: (СТРОГО 2-3 речення. Один сильний експертний інсайт. 
    Якщо доречно — одна нативна згадка конкретної моделі Škoda. 
    ЗАБОРОНЕНО: довгі міркування, філософські паралелі, повтор фактів зі статті.)

    Після вердикту — ЗАВЖДИ одне коротке питання від Агента Софії особисто, конкретне по темі статті. 
    Формат питання: починай з тегу <i> і закінчуй тегом </i>.
    Приклади стилю: "<i>А ви б обрали електро чи бензин? Пишіть 👇</i>". 
    Питання має природно випливати з теми статті і бути цікавим для аудиторії автосалону.

    ТЕКСТ: {article_text_trimmed}
    """

    models = [
        'gemini-flash-lite-latest',
        'gemini-3.1-flash-lite-preview',
        'gemini-flash-latest'
    ]

    for m in models:
        try:
            response = client.models.generate_content(model=m, contents=prompt)
            raw_text = response.text

            # 1. Тотальне очищення від усіх можливих жирних тегів, щоб уникнути вкладеності
            cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', raw_text) # прибираємо маркдаун
            cleaned_text = re.sub(r'</?b>', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'</?strong>', '', cleaned_text, flags=re.IGNORECASE)

            # 2. Форматуємо списки
            cleaned_text = cleaned_text.replace('\n* ', '\n• ')
            cleaned_text = cleaned_text.replace('\n- ', '\n• ')

            # 3. Надійно встановлюємо жирний шрифт для заголовків блоків
            headers_to_bold = ['Суть:', 'Ключові факти:', 'Вердикт Агента Софії:']
            for header in headers_to_bold:
                cleaned_text = cleaned_text.replace(header, f"<b>{header}</b>")

            # 4. Виділяємо Škoda та моделі ТІЛЬКИ в тілі тексту (щоб не зламати заголовок [TITLE])
            if "[TITLE]:" in cleaned_text:
                parts = cleaned_text.split("[TITLE]:", 1)
                before_title = parts[0]
                after_title = parts[1]
                
                if "\n" in after_title:
                    title_text, body_text = after_title.split("\n", 1)
                else:
                    title_text, body_text = after_title, ""
                    
                # Робимо жирними бренди тільки в тілі тексту
                body_text = re.sub(r'(?i)\b(Skoda|Škoda)\b', '<b>Škoda</b>', body_text)
                models_pattern = r'(?i)\b(Fabia|Scala|Octavia|Superb|Kamiq|Karoq|Kodiaq|Enyaq)\b'
                body_text = re.sub(models_pattern, r'<b>\1</b>', body_text)
                
                cleaned_text = f"{before_title}[TITLE]:{title_text}\n{body_text}"
            else:
                # Якщо раптом [TITLE] немає, просто застосовуємо до всього
                cleaned_text = re.sub(r'(?i)\b(Skoda|Škoda)\b', '<b>Škoda</b>', cleaned_text)
                models_pattern = r'(?i)\b(Fabia|Scala|Octavia|Superb|Kamiq|Karoq|Kodiaq|Enyaq)\b'
                cleaned_text = re.sub(models_pattern, r'<b>\1</b>', cleaned_text)

            # 5. Прибираємо можливі артефакти Gemini (якщо модель додає системний текст в кінці)
            cleaned_text = re.sub(r'СЦЕНАРІЙ\s+\d+.*$', '', cleaned_text, flags=re.DOTALL).strip()

            print(f"✅ Модель {m} відповіла успішно.")
            return cleaned_text

        except Exception as e:
            print(f"⚠️ Модель {m} не відповіла: {type(e).__name__}: {e}")
            continue

    return "⚠️ Помилка ШІ: всі моделі Gemini не відповіли. Перевір квоту або API-ключ."
