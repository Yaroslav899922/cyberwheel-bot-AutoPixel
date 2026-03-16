import feedparser
import os
import time
import main   # твій парсер тексту
import brain  # твій Gemini

# 1. СПИСОК ДЖЕРЕЛ (додавай будь-які RSS посилання у sources.txt)
def load_sources():
    if not os.path.exists("sources.txt"):
        # Якщо файлу немає, повертаємо дефолтні
        return ["https://ain.ua/feed/"]
    with open("sources.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

RSS_SOURCES = load_sources()

DB_FILE = "parsed_urls.txt"

def load_processed_urls():
    if not os.path.exists(DB_FILE):
        return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_processed_url(url):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def run_auto_scout():
    print("🛰️ Запуск автоматичного моніторингу новин...")
    processed_urls = load_processed_urls()
    
    for rss_url in RSS_SOURCES:
        print(f"\n📡 Перевіряю: {rss_url}")
        feed = feedparser.parse(rss_url)
        
        # Беремо останні 3 новини з кожного джерела
        for entry in feed.entries[:3]:
            if entry.link not in processed_urls:
                print(f"🆕 Нова стаття знайдена: {entry.title}")
                
                # Крок А: Парсимо повний текст статті
                print("⏳ Завантажую повний текст...")
                article_text = main.fetch_article_data(entry.link)
                
                if article_text:
                    # Крок Б: Робимо ШІ-дайджест
                    print("🧠 Gemini аналізує зміст...")
                    summary = brain.summarize_text(article_text)
                    
                    # Крок В: Виводимо і відправляємо результат
                    final_message = f"✨ **{entry.title}** ✨\n\n{summary}\n\n🔗 [Джерело]({entry.link})"
                    print("\n" + "✨ ГОТОВИЙ ДАЙДЖЕСТ ✨")
                    print(final_message)
                    print("-" * 40)
                    
                    # Відправка у Telegram
                    import telegram_bot
                    telegram_bot.send_telegram_message(final_message)
                    
                    # Крок Г: Запам'ятовуємо посилання
                    save_processed_url(entry.link)
                    processed_urls.add(entry.link)
                    
                    # Пауза, щоб не навантажувати API
                    time.sleep(3)
                else:
                    print("⚠️ Не вдалося отримати текст статті, пропускаю.")
            else:
                print(f"✅ Вже оброблено: {entry.title}")

def run_scheduler():
    import web_server
    import pytz
    from datetime import datetime

    kyiv_tz = pytz.timezone('Europe/Kiev')
    print("🚀 Автоматичний планувальник запущено!")
    print("🌐 Запускаю фоновий веб-сервер для хмари (щоб не засинав)...")
    
    # Запускаємо заглушку-сервер
    web_server.keep_alive()

    while True:
        now = datetime.now(kyiv_tz)
        print(f"\n⏰ Поточний час у Києві: {now.strftime('%H:%M:%S')}")

        try:
            run_auto_scout()
        except Exception as e:
            print(f"❌ Критична помилка під час сканування: {e}")

        # Рахуємо наступний сон
        now_after_scan = datetime.now(kyiv_tz)
        if 6 <= now_after_scan.hour < 23:
            sleep_hours = 1.5
            print(f"☀️ Денний режим. Йду спати на {sleep_hours} год...")
        else:
            sleep_hours = 2
            print(f"🌙 Нічний режим. Йду спати на {sleep_hours} год...")
        
        # Спимо
        time.sleep(sleep_hours * 3600)

if __name__ == "__main__":
    run_scheduler()