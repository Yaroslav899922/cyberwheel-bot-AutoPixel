import sys
import os
from google import genai

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

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
    
    # Використовуємо 'gemini-2.0-flash-exp' (це найновіша робоча версія 2.0)
    # Якщо вона не спрацює, скрипт миттєво переключиться на 1.5-flash
    models_to_try = ['gemini-2.0-flash-exp', 'gemini-1.5-flash']
    
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
    print(summarize_text("Тест зв'язку"))
