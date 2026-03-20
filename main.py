import sys
import requests
import random
import nltk
from newspaper import Article

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')

try:
    nltk.download('punkt_tab', quiet=True)
except:
    pass

# ✅ Ротація User-Agent — обходимо блокування
USER_AGENTS = [
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,uk;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }

def fetch_article_data(url):
    print(f"\n--- 🔍 Аналізую посилання: {url} ---")
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)

        # При 403 — пробуємо з іншим User-Agent
        if response.status_code == 403:
            print(f"⚠️ 403 — пробуємо інший User-Agent...")
            for ua in USER_AGENTS:
                r2 = requests.get(url, headers={'User-Agent': ua, 'Accept': 'text/html'}, timeout=15)
                if r2.status_code == 200:
                    response = r2
                    break

        if response.status_code != 200:
            print(f"❌ Помилка: Сервер повернув код {response.status_code}")
            return None

        article = Article(url, language='uk')
        article.set_html(response.text)
        article.parse()

        if not article.text:
            print("⚠️ Текст не знайдено на сторінці.")
            return None

        print(f"✅ ЗАГОЛОВОК: {article.title}")
        print(f"🖼️ КАРТИНКА ЗНАЙДЕНА: {'Так' if article.top_image else 'Ні'}")
        print("-" * 30)

        return {
            "text": article.text,
            "image": article.top_image,
            "title": article.title
        }

    except Exception as e:
        print(f"❌ Виникла помилка: {type(e).__name__}: {e}")
        return None

if __name__ == "__main__":
    from brain import summarize_text
    print("\n👋 Привіт! Я CyberWheel Parser.\n")
    while True:
        link = input("\n🔗 Встав посилання (або Enter для виходу): ").strip()
        if not link:
            print("👋 До побачення!")
            break
        data = fetch_article_data(link)
        if data:
            print("\n🧠 Gemini аналізує зміст...\n")
            summary = summarize_text(data['text'], data['title'], is_morning=False)
            print("\n" + "="*50)
            print(summary)
        else:
            print("❌ Не вдалося отримати дані.")
