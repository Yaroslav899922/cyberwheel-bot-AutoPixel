import feedparser
import os
import time
import pytz
import schedule
from datetime import datetime, date
import main
import brain
import telegram_bot
import autoconsulting_parser
import morning_digest

DB_FILE          = "parsed_urls.txt"
DIGEST_DATE_FILE = "last_digest_date.txt"  # зберігає дату останньої відправки дайджесту

# ─────────────────────────────────────────────────────────────
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
    """Перевіряє чи дайджест вже відправлявся сьогодні."""
    if not os.path.exists(DIGEST_DATE_FILE):
        return False
    with open(DIGEST_DATE_FILE, "r") as f:
        last_date = f.read().strip()
    return last_date == str(date.today())

def mark_digest_sent():
    """Записує сьогоднішню дату після відправки дайджесту."""
    with open(DIGEST_DATE_FILE, "w") as f:
        f.write(str(date.today()))

# ─────────────────────────────────────────────────────────────
def process_and_send(data, url, processed_urls):
    raw_summary = brain.summarize_text(data['text'], data['title'])

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
        print(f"⚠️ Telegram не отримав повідомлення. Спробуємо наступного разу.")

    time.sleep(10)

# ─────────────────────────────────────────────────────────────
def send_morning_digest():
    """
    Відправляє ранковий дайджест.
    Викликається schedule рівно о 08:00.
    Захищений від повторної відправки через last_digest_date.txt —
    якщо Render перезапустився після 08:00, дайджест не дублюється.
    """
    if was_digest_sent_today():
        print("⏭️ Ранковий дайджест сьогодні вже відправлявся — пропускаємо.")
        return

    print("\n🌅 Відправляю ранковий дайджест...")
    try:
        digest_msg = morning_digest.build_morning_digest()
        success = telegram_bot.send_telegram_message(text=digest_msg)
        if success:
            mark_digest_sent()
            print("✅ Ранковий дайджест відправлено!")
        else:
            print("❌ Дайджест не відправлено — спробуємо наступного разу.")
    except Exception as e:
        print(f"❌ Помилка дайджесту: {type(e).__name__}: {e}")

    # Пауза 30 хвилин після дайджесту перед новинами
    # Використовуємо окремий відкладений запуск щоб не блокувати schedule
    print("⏸️ Пауза 30 хвилин перед новинами...")
    time.sleep(1800)
    run_news_scout()  # одразу після паузи запускаємо новини

# ─────────────────────────────────────────────────────────────
def run_news_scout():
    """Парсить новини з усіх джерел. Викликається щогодини і після дайджесту."""
    processed_urls = load_processed_urls()
    cleanup_old_urls()

    # ── БЛОК 1: RSS-джерела ──────────────────────────────────
    for rss_url in RSS_SOURCES:
        print(f"\n📡 Перевіряю RSS: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"❌ RSS {rss_url}: {type(e).__name__}: {e}")
            continue

        new_entries = [e for e in feed.entries if e.link not in processed_urls]
        for entry in new_entries[:3]:
            data = main.fetch_article_data(entry.link)
            if data and data.get('text'):
                print(f"🆕 RSS: {entry.title[:60]}")
                process_and_send(data, entry.link, processed_urls)

    # ── БЛОК 2: AutoConsulting ────────────────────────────────
    print(f"\n{'─'*50}")
    print("🚗 Перевіряю AutoConsulting...")
    try:
        ac_articles = autoconsulting_parser.get_new_articles(processed_urls)
        for article in ac_articles:
            print(f"🆕 AutoConsulting: {article['data']['title'][:60]}")
            process_and_send(article['data'], article['url'], processed_urls)
    except Exception as e:
        print(f"❌ AutoConsulting: {type(e).__name__}: {e}")

# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import web_server

    print("🌐 Запускаю фоновий веб-сервер...")
    web_server.keep_alive()

    print("🚀 CyberWheel стартував з планувальником!")

    # ── РОЗКЛАД ──────────────────────────────────────────────
    # Дайджест рівно о 08:00 за Києвом
    schedule.every().day.at("08:00").do(send_morning_digest)
    # Новини щогодини
    schedule.every().hour.do(run_news_scout)

    # Одразу при старті — перевіряємо новини (не чекаємо першої години)
    print("🔍 Перший запуск парсингу новин...")
    run_news_scout()

    print("📅 Планувальник активний. Дайджест о 08:00, новини щогодини.")

    while True:
        schedule.run_pending()
        time.sleep(30)  # перевіряємо розклад кожні 30 секунд
