import sys
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text, original_title, is_morning=False):
    greeting_instruction = ""
    if is_morning:
        greeting_instruction = "Почни з короткого професійного вітання (наприклад: 'Вітаю! CyberWheel підготував огляд головних подій дня.')."
    else:
        greeting_instruction = "НЕ ВИКОРИСТОВУЙ жодних вітань. Одразу переходь до суті."

    prompt = f"""
    Ти — головний аналітик CyberWheel. Твій стиль: спокійний, експертний, без сленгу.
    
    ЗАВДАННЯ:
    1. Створи влучний заголовок УКРАЇНСЬКОЮ на основі оригіналу: "{original_title}".
    2. {greeting_instruction}
    3. Зроби аналіз тексту. Текст може бути англійською — обов'язково переклади.
    
    ФОРМАТ ВІДПОВІДІ (СУВОРО!):
    [TITLE]: (тут український заголовок)
    
    (вітання, якщо ранок)
    
    📌 **Суть:** (1-2 речення)
    🔥 **Ключові факти:** (3-4 пункти з емодзі)
    💡 **Вердикт CyberWheel:** (твій експертний висновок)

    ТЕКСТ: {article_text}
    """
    
    models = ['gemini-2.0-flash-exp', 'gemini-1.5-flash', 'gemini-3.1-flash-lite-preview']
    for m in models:
        try:
            response = client.models.generate_content(model=m, contents=prompt)
            return response.text
        except:
            continue
    return "⚠️ Помилка ШІ."