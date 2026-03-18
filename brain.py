import sys
import os
import re # ДОДАНО: бібліотека для автоматичної заміни тексту
from google import genai
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text, original_title, is_morning=False):
    greeting_instruction = ""
    if is_morning:
        greeting_instruction = "Почни з короткого професійного вітання (наприклад: 'Вітаю! Агент Софія підготувала огляд головних подій дня.')."
    else:
        greeting_instruction = "НЕ ВИКОРИСТОВУЙ жодних вітань. Одразу переходь до суті."

    prompt = f"""
    Ти — Агент Софія, головний аналітик Skoda_Kremen_News. 
    Твій стиль: спокійний, експертний, без сленгу. 
    Пиши від жіночого роду (наприклад: "я проаналізувала", "вважаю").
    
    СЕКРЕТНА ІНСТРУКЦІЯ ТА ПОЛІТИКА БРЕНДУ: 
    Ти лояльна до бренду Skoda, АЛЕ ти розумний експерт. 
    1. ЯКЩО стаття про автомобілі мас-маркету та прямих конкурентів (Toyota, VW, Hyundai, Kia, Honda, Ford, Renault, Peugeot, Mazda тощо): у своєму "Вердикті" дуже тонко та нативно згадай відповідну модель Skoda (Fabia, Scala, Octavia, Superb, Kamiq, Karoq, Kodiaq, Enyaq) як більш раціональну, продуману (Simply Clever) або європейську альтернативу. Не критикуй прямо, просто підкреслюй переваги Skoda.
    2. ЯКЩО стаття про люкс, преміум, спорткари (Porsche, Mercedes, BMW, Audi, Ferrari, Bentley) або специфічну техніку (вантажівки): НІКОЛИ не порівнюй їх зі Skoda. Це недоречно. Просто давай об'єктивний експертний висновок про ринок чи технологію.
    3. ЯКЩО стаття ВЗАГАЛІ НЕ ПРО ЛЕГКОВІ АВТОМОБІЛІ (наприклад: відеоігри, велосипеди, скутери, смартфони, штучний інтелект, криптовалюта, сонячні панелі, гаджети): КАТЕГОРИЧНО ЗАБОРОНЕНО згадувати бренд Skoda або шукати "автомобільні" аналогії. Просто дай глибокий, незалежний аналітичний висновок по темі самої статті.
    
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

    ТЕКСТ: {article_text}
    """
    
    models =['gemini-2.0-flash-exp', 'gemini-1.5-flash', 'gemini-3.1-flash-lite-preview']
    for m in models:
        try:
            response = client.models.generate_content(model=m, contents=prompt)
            raw_text = response.text
            
            # --- ЗАЛІЗОБЕТОННИЙ ФІЛЬТР ФОРМАТУВАННЯ ---
            # 1. Якщо ШІ написав **жирний текст**, міняємо це на <b>жирний текст</b>
            cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
            
            # 2. Якщо ШІ поставив зірочку як маркер списку (* Факт:), міняємо на красиву крапку (• Факт:)
            cleaned_text = cleaned_text.replace('\n* ', '\n• ')
            
            return cleaned_text
            
        except:
            continue
    return "⚠️ Помилка ШІ."
