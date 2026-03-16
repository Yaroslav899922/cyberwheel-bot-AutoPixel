import sys
import os # Додано для роботи зі змінними оточення
from google import genai

# Налаштування для тексту (вирішує проблему з емодзі у терміналі Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

# ТЕПЕР МИ НЕ ПИШЕМО КЛЮЧ ТУТ ПРЯМИМ ТЕКСТОМ
# Коли ви запустите це на Render, ми вкажемо цей ключ у налаштуваннях
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Налаштування моделі через новий пакет google-genai
client = genai.Client(api_key=GOOGLE_API_KEY)

def summarize_text(article_text):
    """Функція відправляє текст у Gemini і отримує вижимку"""
    
    prompt = f"""
    Ти — крутий український техно- та авто-блогер. Тобі надіслали текст статті.
    УВАГА: Текст нижче може бути будь-якою мовою (включно з англійською). Обов'язково працюй як перекладач і редактор.
    Твоя задача — зробити з нього стислий, цікавий дайджест виключно та обов'язково УКРАЇНСЬКОЮ мовою.
    
    Формат відповіді:
    📌 **Про що мова:** (1 речення)
    🔥 **Головні тези:** (3-4 пункти)
    💡 **Чому це важливо:** (короткий висновок)

    Ось текст статті:
    {article_text}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', # Повернув стабільну версію для Render
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Помилка ШІ: {e}"

if __name__ == "__main__":
    # Маленький тест
    print("🧠 Gemini думає над тестовим запитом...")
    test_result = summarize_text("Штучний інтелект — це здатність машин мислити як люди.")
    print("\n--- ВІДПОВІДЬ ШІ ---")
    print(test_result)