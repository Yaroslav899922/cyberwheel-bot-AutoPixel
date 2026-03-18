import feedparser
import os
import time
import pytz
from datetime import datetime
import main
import brain
import telegram_bot

DB_FILE = "parsed_urls.txt"

# 1. СПИСОК ДЖЕРЕЛ
def load_sources():
    if not os.path.exists("sources.txt"):
        return ["https://ain.ua/feed/"]
    with open("sources.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

RSS_SOURCES = load_sources()

def load_processed_urls():
    if not os.path.exists(DB_FILE):
        return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_processed_url(url):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def run_auto_scout():
    kyiv_tz = pytz.timezone('Europe/Kiev')
    now = datetime.now(kyiv_tz)
    is_morning = (now.hour == 8) # Вітаємося тільки в 8:00
    
    processed_urls = load_processed_urls()
    
    for rss_url in RSS_SOURCES:
        print(f"\n📡 Перевіряю: {rss_url}")
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:3]:
            if entry.link not in processed_urls:
                data = main.fetch_article_data(entry.link)
                if data and data.get('text'):
                    print(f"🆕 Обробка статті: {entry.title}")
                    raw_summary = brain.summarize_text(data['text'], entry.title, is_morning)
                    
                    # Обробка заголовка від ШІ
                    if "[TITLE]:" in raw_summary:
                        parts = raw_summary.split("[TITLE]:", 1)[1].split("\n", 1)
                        # Заголовок великими літерами та жирним (HTML)
                        final_msg = f"⚡️ <b>{parts[0].strip().upper()}</b>\n\n{parts[1].strip()}"
                    else:
                        final_msg = raw_summary

                    # БЛОК СОЦМЕРЕЖ
                    social_links = (
                        "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
                        "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
                        "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
                        "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
                    )
                    final_msg += social_links

                    # Відправка у Telegram (з фото та кнопкою)
                    telegram_bot.send_telegram_message(
                        text=final_msg, 
                        url=entry.link,
                        image_url=data.get('image') 
                    )
                    
                    save_processed_url(entry.link)
                    processed_urls.add(entry.link)
                    time.sleep(5)
            else:
                print(f"✅ Вже було: {entry.title[:40]}...")

if __name__ == "__main__":
    import web_server
    
    print("🌐 Запускаю фоновий веб-сервер...")
    web_server.keep_alive()
    
    print("🚀 Автоматичний планувальник CyberWheel стартував!")
    
    while True:
        try:
            # Одразу запускаємо перевірку при старті
            run_auto_scout()
        except Exception as e:
            print(f"❌ Критична помилка у циклі: {e}")
            
        # Після перевірки засинаємо на 60 хвилин (3600 секунд)
        print("😴 Патрулювання завершено. Наступна перевірка через 60 хвилин...")
        time.sleep(3600)
