import feedparser
import os
import time
import pytz
from datetime import datetime
import main
import brain
import telegram_bot
import autoconsulting_parser
import morning_digest  # ✅ НОВЕ: ранковий дайджест

DB_FILE = "parsed_urls.txt"

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

def cleanup_old_urls(max_lines=2000):
    if not os.path.exists(DB_FILE):
        return
    with open(DB_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if len(lines) > max_lines:
        print(f"🧹 Очищення бази: {len(lines)} → {max_lines} записів")
        with open(DB_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[-max_lines:]) + "\n")

def process_and_send(data, url, is_morning, processed_urls):
    raw_summary = brain.summarize_text(data['text'], data['title'], is_morning)

    if "[TITLE]:" in raw_summary:
        parts = raw_summary.split("[TITLE]:", 1)[1].split("\n", 1)
        final_msg = f"⚡️ <b>{parts[0].strip().upper()}</b>\n\n{parts[1].strip()}"
    else:
        final_msg = raw_summary

    social_links = (
        "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
        "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
        "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
        "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
    )
    final_msg += social_links

    success = telegram_bot.send_telegram_message(
        text=final_msg,
        url=url,
        image_url=data.get('image')
    )

    if success:
        save_processed_url(url)
        processed_urls.add(url)
        print(f"✅ URL збережено: {url[:60]}...")
    else:
        print(f"⚠️ Telegram не отримав повідомлення. URL не збережено — спробуємо наступного разу.")

    time.sleep(10)

def run_auto_scout():
    kyiv_tz = pytz.timezone('Europe/Kiev')
    now = datetime.now(kyiv_tz)
    is_morning = (now.hour == 8)

    cleanup_old_urls()
    processed_urls = load_processed_urls()

    # ── РАНКОВИЙ ДАЙДЖЕСТ о 8:00 ────────────────────────────────────────────
    if is_morning:
        print("\n🌅 Відправляю ранковий дайджест...")
        try:
            digest_msg = morning_digest.build_morning_digest()
            # Дайджест без кнопки "Читати оригінал" і без фото — чистий текст
            telegram_bot.send_telegram_message(text=digest_msg)
            print("✅ Ранковий дайджест відправлено!")
        except Exception as e:
            print(f"❌ Помилка дайджесту: {type(e).__name__}: {e}")

    # ── БЛОК 1: RSS-джерела ──────────────────────────────────────────────────
    for rss_url in RSS_SOURCES:
        print(f"\n📡 Перевіряю RSS: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"❌ Не вдалося завантажити RSS {rss_url}: {type(e).__name__}: {e}")
            continue

        new_entries = [e for e in feed.entries if e.link not in processed_urls]

        for entry in new_entries[:3]:
            data = main.fetch_article_data(entry.link)
            if data and data.get('text'):
                print(f"🆕 RSS стаття: {entry.title}")
                process_and_send(data, entry.link, is_morning, processed_urls)

    # ── БЛОК 2: AutoConsulting ───────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"🚗 Перевіряю AutoConsulting...")
    try:
        ac_articles = autoconsulting_parser.get_new_articles(processed_urls)
        for article in ac_articles:
            print(f"🆕 AutoConsulting стаття: {article['data']['title'][:60]}")
            process_and_send(article['data'], article['url'], is_morning, processed_urls)
    except Exception as e:
        print(f"❌ Помилка AutoConsulting парсера: {type(e).__name__}: {e}")

if __name__ == "__main__":
    import web_server

    print("🌐 Запускаю фоновий веб-сервер...")
    web_server.keep_alive()

    print("🚀 Автоматичний планувальник CyberWheel стартував!")

    while True:
        try:
            run_auto_scout()
        except Exception as e:
            print(f"❌ Критична помилка у циклі: {type(e).__name__}: {e}")

        print("😴 Патрулювання завершено. Наступна перевірка через 60 хвилин...")
        time.sleep(3600)
