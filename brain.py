import sys
import os
from google import genai

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text):
    prompt = f"""
    Ти — провідний український техно-блогер та авто-експерт рівня ТОП. 
    Твоя задача — зробити інтелектуальний, соковитий та професійний дайджест статті УКРАЇНСЬКОЮ мовою.
    Текст може бути англійською — переклади, адаптуй та додай контексту.
    
    Стиль: енергійний, експертний, з легким розмовним відтінком (як для Telegram-каналу "CyberWheel").
    
    Формат відповіді:
    (Твій авторський вступ: "Йоу, народ! Оце новина...", "Привіт, CyberWheel-спільното!")
    
    📌 **Про що мова:** (1 влучне речення)
    🔥 **Головні тези:** (3-4 пункти з емодзі та деталями)
    💡 **Чому це важливо:** (твій глибокий аналітичний висновок)

    Ось текст статті:
    {article_text}
    """
    
    # Пріоритет моделей: 3.1 Pro (найрозумніша) -> 3.1 Flash (найшвидша) -> 2.0/1.5 (резерв)
    models_to_try = [
        'gemini-3.1-pro-preview', 
        'gemini-3.1-flash-lite-preview', 
        'gemini-1.5-flash'
    ]
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"⚠️ Модель {model_name} недоступна, пробую наступну...")
            last_error = e
            continue 
            
    return f"⚠️ Помилка ШІ: {last_error}"

if __name__ == "__main__":
    print(summarize_text("Тестовий текст про майбутнє автономних транспортних засобів."))
