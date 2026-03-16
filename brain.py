import sys
import os
from google import genai
from dotenv import load_dotenv # Додано для локальних ключів

# Завантажуємо змінні з файлу .env (якщо він є)
load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

# Тепер ключ буде братися або з .env (локально), або з налаштувань Render (у хмарі)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text):
    prompt = f"""
    Ти — крутий український техно-блогер CyberWheel. 
    Зроби соковитий дайджест статті УКРАЇНСЬКОЮ мовою.
    Текст може бути англійською — переклади та адаптуй.
    
    Стиль: розмовний, з емодзі, професійний.
    📌 **Про що мова:** (1 речення)
    🔥 **Головні тези:** (3-4 пункти)
    💡 **Чому це важливо:** (висновок)

    Текст статті:
    {article_text}
    """
    
    # Використовуємо найнадійніші моделі
    models_to_try = [
        'gemini-2.0-flash-exp', 
        'gemini-1.5-flash',
        'gemini-3.1-flash-lite-preview' # Додав твою улюблену 3.1 як запасну
    ]
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text
        except Exception:
            continue 
            
    return "⚠️ ШІ тимчасово перевантажений. Спробую пізніше."

if __name__ == "__main__":
    # Тест для перевірки, чи підтягнувся ключ
    if not GOOGLE_API_KEY:
        print("❌ ПОМИЛКА: Ключ GOOGLE_API_KEY не знайдено! Перевір файл .env")
    else:
        print("🧠 Gemini підключено. Думаю над тестом...")
        print(summarize_text("Штучний інтелект стає основою сучасних авто."))