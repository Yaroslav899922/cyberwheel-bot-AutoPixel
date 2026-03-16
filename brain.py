import sys
import os
from google import genai

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text):
    """Функція відправляє текст у Gemini і отримує вижимку"""
    
    prompt = f"""
    Ти — професійний український техно-блогер та авто-експерт. 
    Твоя задача — проаналізувати статтю та зробити з неї стислий, "соковитий" дайджест УКРАЇНСЬКОЮ мовою.
    Текст може бути англійською — переклади та адаптуй його.
    
    Формат відповіді:
    📌 **Про що мова:** (1 влучне речення)
    🔥 **Головні тези:** (3-4 пункти з емодзі)
    💡 **Чому це важливо:** (короткий експертний висновок)

    Ось текст статті:
    {article_text}
    """
    
    try:
        # Використовуємо актуальну модель 2.0 Flash Experimental
        # Якщо ця видасть 404, змініть на 'gemini-2.0-flash-lite-preview-02-05'
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', 
            contents=prompt,
        )
        return response.text
    except Exception as e:
        # Якщо 2.0 все ж не пускає, скрипт автоматично спробує 1.5, щоб бот не падав
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
            )
            return response.text
        except:
            return f"Помилка ШІ: {e}"

if __name__ == "__main__":
    print("🧠 Gemini 2.0 думає...")
    test_result = summarize_text("Штучний інтелект — це майбутнє автопрому.")
    print(test_result)
