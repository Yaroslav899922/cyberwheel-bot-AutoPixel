import feedparser
import os
import time
import pytz
from datetime import datetime
import main
import brain
import telegram_bot
DB_FILE = "parsed_urls.txt"
RSS_SOURCES =[]
if os.path.exists("sources.txt"):
with open("sources.txt", "r", encoding="utf-8") as f:
RSS_SOURCES =[line.strip() for line in f if line.strip()]
def load_processed_urls():
if not os.path.exists(DB_FILE): return set()
with open(DB_FILE, "r", encoding="utf-8") as f: return set(line.strip() for line in f)
def save_processed_url(url):
with open(DB_FILE, "a", encoding="utf-8") as f: f.write(url + "\n")
def run_auto_scout():
kyiv_tz = pytz.timezone('Europe/Kiev')
now = datetime.now(kyiv_tz)
is_morning = (now.hour == 8) # Вітаємося тільки в 8:00 в першому повідомленні
code
Code
processed_urls = load_processed_urls()

for rss_url in RSS_SOURCES:
    feed = feedparser.parse(rss_url)
    for entry in feed.entries[:3]:
        if entry.link not in processed_urls:
            data = main.fetch_article_data(entry.link)
            if data and data['text']:
                raw_summary = brain.summarize_text(data['text'], entry.title, is_morning)
                
                # Обробка заголовка від ШІ
                if "[TITLE]:" in raw_summary:
                    parts = raw_summary.split("[TITLE]:", 1)[1].split("\n", 1)
                    
                    # ТУТ ЮВЕЛІРНА ПРАВКА: <b> робить жирним, .upper() робить ВЕЛИКИМИ
                    final_msg = f"⚡️ <b>{parts[0].strip().upper()}</b>\n\n{parts[1].strip()}"
                else:
                    final_msg = raw_summary

                # === ДОДАНО: БЛОК З ПОСИЛАННЯМИ НА СОЦМЕРЕЖІ ТА САЙТ ===
                social_links = (
                    "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
                    "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
                    "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
                    "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
                )
                final_msg += social_links
                # ========================================================

                # ХІРУРГІЧНА ПРАВКА: Передаємо боту картинку (image_url)!
                telegram_bot.send_telegram_message(
                    text=final_msg, 
                    url=entry.link,
                    image_url=data.get('image') 
                )
                
                save_processed_url(entry.link)
                time.sleep(5)
if name == "main":
import web_server
code
Code
print("🌐 Запускаю фоновий веб-сервер...")
web_server.keep_alive()

print("🚀 Автоматичний планувальник CyberWheel стартував!")

while True:
    try:
        # Одразу запускаємо перевірку при старті
        run_auto_scout()
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        
    # Після перевірки засинаємо на 60 хвилин (3600 секунд)
    print("😴 Патрулювання завершено. Наступна перевірка через 60 хвилин...")
    time.sleep(3600)
