import sys
import requests
import nltk
from newspaper import Article

# 1. Налаштування для тексту (твоє рішення для емодзі та української у Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')  # type: ignore

try:
    nltk.download('punkt_tab', quiet=True)
except:
    pass

def fetch_article_data(url):
    """
    Завантажує статтю та повертає текст і посилання на головне зображення.
    """
    print(f"\n--- 🔍 Аналізую посилання: {url} ---")
    
    # Використовуємо реалістичний User-Agent, щоб сайти не блокували нас як бота
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }

    try:
        # Спершу завантажуємо сторінку через requests
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Помилка: Сервер повернув код {response.status_code}")
            return None

        # Передаємо HTML у newspaper3k для очищення
        article = Article(url, language='uk')
        article.set_html(response.text)
        article.parse()
        
        if not article.text:
            print("⚠️ Текст не знайдено на сторінці.")
            return None

        print(f"✅ ЗАГОЛОВОК: {article.title}")
        print(f"🖼️ КАРТИНКА ЗНАЙДЕНА: {'Так' if article.top_image else 'Ні'}")
        print("-" * 30)
        
        # Повертаємо результат у вигляді словника (потрібно для Telegram та ШІ)
        return {
            "text": article.text,
            "image": article.top_image,
            "title": article.title
        }

    except Exception as e:
        print(f"❌ Виникла помилка: {e}")
        return None

# --- БЛОК ДЛЯ РУЧНОГО ТЕСТУВАННЯ ---
if __name__ == "__main__":
    from brain import summarize_text

    print("\n👋 Привіт! Я CyberWheel Parser. Дай мені посилання, і я зроблю аналіз.\n")

    while True:
        link = input("\n🔗 Встав посилання (або Enter для виходу): ").strip()
        
        if not link:
            print("👋 До побачення!")
            break

        data = fetch_article_data(link)
        
        if data:
            print("\n🧠 Gemini аналізує зміст...\n")
            # Передаємо в ШІ текст та оригінальний заголовок (для перекладу)
            summary = summarize_text(data['text'], data['title'], is_morning=False)
            
            print("\n" + "="*50)
            print("                 РЕЗУЛЬТАТ АНАЛІЗУ                 ")
            print("="*50)
            print(summary)
        else:
            print("❌ Не вдалося отримати дані. Спробуй інше посилання.")