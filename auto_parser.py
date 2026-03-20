import feedparser
import os
import time
import pytz
import schedule
import email.utils
from datetime import datetime, date
import main
import brain
import telegram_bot
import autoconsulting_parser
import morning_digest

DB_FILE          = "parsed_urls.txt"
DIGEST_DATE_FILE = "last_digest_date.txt"
KYIV_TZ          = pytz.timezone("Europe/Kiev")

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

def was_digest_sent_today():
    if not os.path.exists(DIGEST_DATE_FILE):
        return False
    with open(DIGEST_DATE_FILE, "r") as f:
        return f.read().strip() == str(date.today())

def mark_digest_sent():
    with open(DIGEST_DATE_FILE, "w") as f:
        f.write(str(date.today()))

def get_today_kyiv():
    return datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

def is_entry_today(entry):
    """
    ✅ ВИПРАВЛЕНО: правильна обробка таймзон з RSS.
    Підтримує +0200, -0400, UTC та інші формати.
    """
    today = get_today_kyiv()

    # Спочатку пробуємо через рядок published — найточніший метод
    published_str = getattr(entry, "published", "")
    if published_str:
        try:
            dt = email.utils.parsedate_to_datetime(published_str)
            entry_date = dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
            return entry_date == today
        except Exception:
            pass

    # Запасний — через published_parsed (feedparser конвертує в UTC)
    published = getattr(entry, "published_parsed", None)
    if not published:
        return True  # якщо дати нема — пропускаємо (дозволяємо)
    try:
        entry_dt   = datetime(*published[:6], tzinfo=pytz.utc)
        entry_date = entry_dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
        return entry_date == today
    except Exception:
        return True

def process_and_send(data, url, processed_urls):
    raw_summary = brain.summarize_text(data['text'], data['title'])

    if "[TITLE]:" in raw_summary:
        parts     = raw_summary.split("[TITLE]:", 1)[1].split("\n", 1)
        final_msg = f"⚡️ <b>{parts[0].strip().upper()}</b>\n\n{parts[1].strip()}"
    else:
        final_msg = raw_summary

    source_link  = f"\n\n<a href='{url}'><b>Читати повністю →</b></a>" if url else ""
    social_links = (
        "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
        "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
        "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
        "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
    )
    final_msg += source_link + social_links

    success = telegram_bot.send_telegram_message(
        text=final_msg,
        url=None,
        image_url=data.get('image')
    )

    if success:
        save_processed_url(url)
        processed_urls.add(url)
        print(f"✅ Збережено: {url[:60]}...")
    else:
        print(f"⚠️ Не відправлено — спробуємо наступного разу.")

    time.sleep(10)

def send_morning_digest():
    if was_digest_sent_today():
        print("⏭️ Дайджест сьогодні вже відправлявся.")
        return
    print("\n🌅 Відправляю ранковий дайджест...")
    try:
        digest_msg = morning_digest.build_morning_digest()
        success    = telegram_bot.send_telegram_message(text=digest_msg)
        if success:
            mark_digest_sent()
            print("✅ Дайджест відправлено!")
    except Exception as e:
        print(f"❌ Помилка дайджесту: {type(e).__name__}: {e}")

def run_news_scout():
    today          = get_today_kyiv()
    processed_urls = load_processed_urls()
    cleanup_old_urls()

    print(f"\n🔍 Парсинг новин за {today}")
    print(f"📋 RSS джерел: {len(RSS_SOURCES)}")

    # ── БЛОК 1: RSS ──────────────────────────────────────────
    for rss_url in RSS_SOURCES:
        print(f"\n📡 RSS: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
            print(f"   Всього в стрічці: {len(feed.entries)}")
        except Exception as e:
            print(f"❌ Помилка RSS {rss_url}: {type(e).__name__}: {e}")
            continue

        new_entries = [
            e for e in feed.entries
            if e.link not in processed_urls and is_entry_today(e)
        ]
        print(f"   Сьогоднішніх нових: {len(new_entries)}")

        for entry in new_entries[:5]:
            data = main.fetch_article_data(entry.link)
            if data and data.get('text'):
                print(f"🆕 RSS: {entry.title[:60]}")
                process_and_send(data, entry.link, processed_urls)
            else:
                # ✅ Битий URL — записуємо щоб не перевіряти знову
                print(f"⏭️ Не вдалось отримати текст — пропускаємо: {entry.link[:60]}")
                save_processed_url(entry.link)
                processed_urls.add(entry.link)

    # ── БЛОК 2: AutoConsulting ────────────────────────────────
    print(f"\n{'─'*50}")
    print("🚗 AutoConsulting...")
    try:
        ac_articles = autoconsulting_parser.get_new_articles(processed_urls, max_total=3)
        for article in ac_articles:
            print(f"🆕 AutoConsulting: {article['data']['title'][:60]}")
            process_and_send(article['data'], article['url'], processed_urls)
    except Exception as e:
        print(f"❌ AutoConsulting: {type(e).__name__}: {e}")

if __name__ == "__main__":
    import web_server

    print("🌐 Запускаю фоновий веб-сервер...")
    web_server.keep_alive()

    print("🚀 CyberWheel стартував!")

    # 08:00 UTC = 10:00 Київ — дайджест
    schedule.every().day.at("08:00").do(send_morning_digest)
    # 08:30 UTC = 10:30 Київ — перші новини після дайджесту
    schedule.every().day.at("08:30").do(run_news_scout)
    # ✅ Новини кожні 60 хвилин після попереднього запуску
    # (не чекає круглої години — запускає через 60 хв після старту)
    schedule.every(60).minutes.do(run_news_scout)

    print("🔍 Перший запуск парсингу при старті...")
    run_news_scout()

    print("📅 Дайджест о 10:00 Київ, новини о 10:30 і щогодини.")

    while True:
        schedule.run_pending()
        time.sleep(30)
