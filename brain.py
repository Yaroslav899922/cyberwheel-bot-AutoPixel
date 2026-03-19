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

# ✅ ВИПРАВЛЕННЯ 4: Секретна інструкція тепер береться з Render → Environment Variables (BRAND_INSTRUCTIONS)
# Якщо змінна не задана на Render — використовується короткий запасний текст нижче.
# Після того як додаси BRAND_INSTRUCTIONS на Render — запасний текст ніколи не спрацює.
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

    # ✅ ВИПРАВЛЕННЯ: обмежуємо розмір статті щоб не перевищити ліміти Gemini
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
    
    ФОРМАТ ВІДПОВІДІ (СУВОРО ДОТРИМУЙСЯ HTML-ТЕГІВ <b>):
    [TITLE]: (тут український заголовок)
    
    (вітання, якщо ранок)
    
    📌 <b>Суть:</b> (1-2 речення)
    🔥 <b>Ключові факти:</b> (3-4 пункти)
    💡 <b>Вердикт Агента Софії:</b> (твій експертний висновок із дотриманням СЕКРЕТНОЇ ІНСТРУКЦІЇ)

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

            # Фільтр форматування — без змін, все як було
            cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
            cleaned_text = cleaned_text.replace('\n* ', '\n• ')
            cleaned_text = re.sub(r'(?i)\b(Skoda|Škoda)\b', '<b>Škoda</b>', cleaned_text)
            models_pattern = r'(?i)\b(Fabia|Scala|Octavia|Superb|Kamiq|Karoq|Kodiaq|Enyaq)\b'
            cleaned_text = re.sub(models_pattern, r'<b>\1</b>', cleaned_text)
            cleaned_text = cleaned_text.replace('<b><b>', '<b>').replace('</b></b>', '</b>')

            print(f"✅ Модель {m} відповіла успішно.")
            return cleaned_text

        except Exception as e:
            # ✅ ВИПРАВЛЕННЯ 3: тепер видно точну причину помилки в логах Render
            print(f"⚠️ Модель {m} не відповіла: {type(e).__name__}: {e}")
            continue

    return "⚠️ Помилка ШІ: всі моделі Gemini не відповіли. Перевір квоту або API-ключ."
