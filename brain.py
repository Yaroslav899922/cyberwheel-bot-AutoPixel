import sys
import os
import re
import time
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
    
    ФОРМАТ ВІДПОВІДІ (СУВОРО ДОТРИМУЙСЯ, НЕ ВИКОРИСТОВУЙ БУДЬ-ЯКІ HTML ТЕГИ ВРУЧНУ):
    [TITLE]: (тут український заголовок)
    
    📌 Суть: (1-2 речення — коротко про що стаття)
    🔥 Ключові факти: (3-4 пункти — тільки найважливіше, без води)
    💡 Вердикт Агента Софії: (СТРОГО 2-3 речення. Один сильний експертний інсайт. 
    Якщо доречно — одна нативна згадка конкретної моделі Škoda. 
    ЗАБОРОНЕНО: довгі міркування, філософські паралелі, повтор фактів зі статті.)

    Після вердикту — ЗАВЖДИ одне коротке питання від Агента Софії особисто, конкретне по темі статті.
    Питання має природно випливати з теми статті і бути цікавим для аудиторії автосалону.
    Формат питання: обов'язково починай з текстового маркера [QUESTION]:
    Приклад: "[QUESTION]: А ви б обрали електро чи бензин? Пишіть 👇"

    ТЕКСТ: {article_text_trimmed}
    """

    models = [
        'gemini-flash-lite-latest',
        'gemini-3.1-flash-lite-preview',
        'gemini-flash-latest'
    ]

    for i, m in enumerate(models):
        try:
            response = client.models.generate_content(model=m, contents=prompt)
            raw_text = response.text

            # 1. Тотальне очищення від усіх можливих жирних тегів
            cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', raw_text) 
            cleaned_text = re.sub(r'</?b>', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'</?strong>', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'</?i>', '', cleaned_text, flags=re.IGNORECASE)

            # 2. Форматуємо списки
            cleaned_text = cleaned_text.replace('\n* ', '\n• ')
            cleaned_text = cleaned_text.replace('\n- ', '\n• ')

            # 3. Надійно встановлюємо жирний шрифт для заголовків блоків
            headers_to_bold = ['Суть:', 'Ключові факти:', 'Вердикт Агента Софії:']
            for header in headers_to_bold:
                cleaned_text = cleaned_text.replace(header, f"<b>{header}</b>")

            # 4. Виділяємо Škoda та моделі ТІЛЬКИ в тілі тексту
            if "[TITLE]:" in cleaned_text:
                parts = cleaned_text.split("[TITLE]:", 1)
                before_title = parts[0]
                after_title = parts[1]
                
                if "\n" in after_title:
                    title_text, body_text = after_title.split("\n", 1)
                else:
                    title_text, body_text = after_title, ""
                    
                body_text = re.sub(r'(?i)\b(Skoda|Škoda)\b', '<b>Škoda</b>', body_text)
                models_pattern = r'(?i)\b(Fabia|Scala|Octavia|Superb|Kamiq|Karoq|Kodiaq|Enyaq)\b'
                body_text = re.sub(models_pattern, r'<b>\1</b>', body_text)
                
                cleaned_text = f"{before_title}[TITLE]:{title_text}\n{body_text}"
            else:
                cleaned_text = re.sub(r'(?i)\b(Skoda|Škoda)\b', '<b>Škoda</b>', cleaned_text)
                models_pattern = r'(?i)\b(Fabia|Scala|Octavia|Superb|Kamiq|Karoq|Kodiaq|Enyaq)\b'
                cleaned_text = re.sub(models_pattern, r'<b>\1</b>', cleaned_text)

            # 5. Прибираємо артефакти Gemini
            cleaned_text = re.sub(r'СЦЕНАРІЙ\s+\d+.*$', '', cleaned_text, flags=re.DOTALL).strip()

            # 6. ЗГОРНУТИЙ ВЕРДИКТ (Collapsible Quote) через [QUESTION]: маркер
            if "[QUESTION]:" in cleaned_text:
                parts = cleaned_text.split("[QUESTION]:", 1)
                main_text = parts[0].strip()
                question_text = parts[1].strip()

                verdict_marker = "<b>Вердикт Агента Софії:</b>"
                if verdict_marker in main_text:
                    v_parts = main_text.split(verdict_marker, 1)
                    before_verdict = v_parts[0]
                    verdict_text = v_parts[1].strip()
                    cleaned_text = (
                        f"{before_verdict}{verdict_marker}\n"
                        f"<blockquote expandable>{verdict_text}</blockquote>\n\n"
                        f"<i>{question_text}</i>"
                    )
                else:
                    print("⚠️ Увага: не знайдено заголовок Вердикту.")
                    cleaned_text = f"{main_text}\n\n<i>{question_text}</i>"
            else:
                print("⚠️ Увага: ШІ не згенерував маркер [QUESTION]:")

            print(f"✅ Модель {m} відповіла успішно.")
            return cleaned_text

        except Exception as e:
            print(f"⚠️ Модель {m} не відповіла: {e}")
            # Пауза тільки якщо: 1) є ще моделі в черзі, 2) причина — перевантаження Google
            if i < len(models) - 1 and ("503" in str(e) or "UNAVAILABLE" in str(e)):
                print("⏳ Сервери перевантажені. Чекаємо 10 секунд перед наступною спробою...")
                time.sleep(10)
            continue

    return "⚠️ Помилка ШІ."
