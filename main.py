import sys
import requests
import nltk
from newspaper import Article

    # Налаштування для тексту
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')  # type: ignore

try:
    nltk.download('punkt_tab')
except:
    pass

def fetch_article_data(url):
    print(f"\n--- 🔍 Тестуємо доступ до: {url} ---")
    
    # Деякі сайти (як Вікіпедія) вимагають вказання бота у User-Agent, інакше блокують (403)
    headers = {
        'User-Agent': 'AI_Parser_Bot/1.0 (contact@example.com)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }

    try:
        # 1. Спершу завантажуємо сторінку через requests
        response = requests.get(url, headers=headers, timeout=15)
        
        print(f"DEBUG: Код відповіді сервера: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Помилка: Сервер повернув код {response.status_code}. Сайт нас блокує.")
            return None

        # 2. Якщо все ок (200), передаємо цей HTML у newspaper3k
        article = Article(url, language='uk')
        article.set_html(response.text) # Передаємо готовий текст сторінки
        article.parse()
        
        if not article.text:
            print("⚠️ Текст не знайдено. Можливо, структура сайту заскладна.")
            return None

        print(f"✅ ЗАГОЛОВОК: {article.title}")
        print("-" * 30)
        print(f"📝 ТЕКСТ (перші 500 символів):\n{article.text[:500]}...")
        print("-" * 30)
        
        return article.text

    except Exception as e:
        print(f"❌ Виникла помилка: {e}")
        return None

if __name__ == "__main__":
    from brain import summarize_text

    print("\n👋 Привіт! Я AI-Парсер. Дай мені посилання на статтю, і я зроблю з неї короткий дайджест.\n")

    while True:
        # Запитуємо посилання у користувача
        link = input("\n🔗 Введіть посилання на статтю (або натисніть Enter для виходу): ").strip()
        
        # Якщо введено порожній рядок - виходимо з програми
        if not link:
            print("👋 До побачення!")
            break

        # 1. Спершу витягуємо текст (Парсер)
        article_text = fetch_article_data(link)
        
        if article_text:
            print("\n🧠 Передаємо текст до Gemini для аналізу...\n")
            # 2. Передаємо текст на аналіз у ШІ (Генератор)
            summary = summarize_text(article_text)
            
            print("\n" + "="*50)
            print("                 ВІДПОВІДЬ ШІ                 ")
            print("="*50)
            print(summary)
        else:
            print("❌ Не вдалося отримати текст статті для аналізу. Спробуйте інше посилання.")