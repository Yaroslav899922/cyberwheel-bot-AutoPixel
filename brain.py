import sys
import os
from google import genai

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text):
    prompt = f"""
    Ти — крутий український техно-блогер. Тобі надіслали текст статті.
    Зроби з нього стислий дайджест УКРАЇНСЬКОЮ мовою.
    
    Формат:
    📌 **Про що мова:** (1 речення)
    🔥 **Головні тези:** (3-4 пункти)
    💡 **Чому це важливо:** (висновок)

    Ось текст: {article_text}
    """
    try:
        # Використовуємо 1.5-flash, вона зараз найстабільніша
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"⚠️ Помилка Gemini: {e}"
