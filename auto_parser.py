import feedparser
import os
import time
import pytz
import schedule
import email.utils
import random
import re
from datetime import datetime, date, timedelta
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

# Стоп-слова для RSS — нерелевантний контент
RSS_STOP_WORDS = [
    "мотоцикл", "мото", "скутер", "квадроцикл",
    "вантажівк", "тягач", "автобус", "тролейбус",
    "трактор", "комбайн", "причіп", "фура",
    "motorcycle", "motorbike", "scooter", "truck", "bus",
]

def is_rss_title_relevant(title):
    """Фільтр нерелевантних RSS статей по заголовку."""
    title_lower = title.lower()
    for word in RSS_STOP_WORDS:
        if word in title_lower:
            print(f"🚫 RSS стоп-слово '{word}': {title[:60]}")
            return False
    return True

def is_entry_recent(entry):
    """
    ✅ ВИПРАВЛЕНО: Дозволяє статті за сьогодні та вчора.
    Так бот зранку підтягне ті новини, які вийшли пізно вночі.
    """
    now = datetime.now(KYIV_TZ)
    allowed_dates = [
        now.strftime("%Y-%m-%d"), 
        (now - timedelta(days=1)).strftime("%Y-%m-%d")
    ]

    # Спочатку пробуємо через рядок published
    published_str = getattr(entry, "published", "")
    if published_str:
        try:
            dt = email.utils.parsedate_to_datetime(published_str)
            entry_date = dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
            return entry_date in allowed_dates
        except Exception:
            pass

    # Запасний — через published_parsed
    published = getattr(entry, "published_parsed", None)
    if not published:
        return True  # якщо дати нема — пропускаємо (дозволяємо)
    try:
        entry_dt   = datetime(*published[:6], tzinfo=pytz.utc)
        entry_date = entry_dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
        return entry_date in allowed_dates
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
        
        # ✅ НОВА ЛОГІКА: Рандомна пауза між публікаціями від 5 до 7 хвилин
        pause_seconds = random.randint(300, 420)
        print(f"⏳ Чекаю {pause_seconds // 60} хв і {pause_seconds % 60} сек перед наступним постом, щоб не спамити...")
        time.sleep(pause_seconds)
    else:
        print(f"⚠️ Не відправлено — спробуємо наступного разу.")

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

# ✅ ОНОВЛЕНА ФУНКЦІЯ: Ідеальний дизайн та правильний тон для вечірнього побажання
def send_evening_message():
    print("\n🌙 Відправляю вечірнє побажання...")
    prompt = """Ти — Агент Софія, куратор автоканалу Skoda_Kremen_News. 
    Напиши коротке побажання на добраніч (1-2 речення).
    Сенс: на сьогодні потік новин завершено, час відпочивати.
    СУВОРІ ПРАВИЛА:
    1. НЕ вітайся (не пиши "Вітаю", "Привіт", "Добрий вечір" тощо — одразу переходь до суті).
    2. НЕ використовуй пафосних слів ("надзвичайно", "неймовірно", "фантастично"). Пиши просто і природно.
    3. Додай легку згадку про комфорт Škoda.
    4. Дозволено виділяти ключові слова (наприклад, назву бренда <b>Škoda</b>) жирним шрифтом, але ТІЛЬКИ через HTML-теги: <b>текст</b>.
    5. КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати зірочки (**) для виділення.
    """
    try:
        response = brain.client.models.generate_content(
            model='gemini-flash-lite-latest',
            contents=prompt
        )
        ai_text = response.text.strip()
        # Про всяк випадок чистимо від можливих зірочок, якщо ШІ їх додасть
        ai_text = re.sub(r'[*_`]', '', ai_text)
        
        # Формуємо фірмовий стиль повідомлення
        final_msg = f"🌙 <b>НА ДОБРАНІЧ</b>\n\n{ai_text}\n\n✨ <i>Ваш Агент Софія</i>"
        
        social_links = (
            "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
            "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
            "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
            "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
        )
        final_msg += social_links

        telegram_bot.send_telegram_message(text=final_msg)
        print("✅ Вечірнє повідомлення відправлено!")
    except Exception as e:
        print(f"❌ Помилка вечірнього повідомлення: {e}")

def run_news_scout():
    # 🌙 ЗАХИСТ ВІД НІЧНОГО ПАРСИНГУ
    current_hour = datetime.now(KYIV_TZ).hour
    if current_hour >= 22 or current_hour < 10:
        print(f"😴 Нічний режим ({current_hour}:00). Парсинг зупинено. Бот відпочиває до 10:00 ранку.")
        return

    today          = get_today_kyiv()
    processed_urls = load_processed_urls()
    cleanup_old_urls()

    print(f"\n🔍 Парсинг новин за {today} (включаючи вчорашні нічні)")
    print(f"📋 RSS джерел: {len(RSS_SOURCES)}")

    # ── БЛОК 1: RSS ──────────────────────────────────────────
    for rss_url in RSS_SOURCES:
        pause = random.uniform(5, 15)
        print(f"⏳ Пауза {pause:.1f}с...")
        time.sleep(pause)

        print(f"\n📡 RSS: {rss_url}")
        try:
            feed = feedparser.parse(
                rss_url,
                agent=random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Feedly/1.0 (+http://www.feedly.com/fetcher.html)",
                    "NewsBlur Feed Fetcher - 250000 subscribers",
                ])
            )
            print(f"   Всього в стрічці: {len(feed.entries)}")
        except Exception as e:
            print(f"❌ Помилка RSS {rss_url}: {type(e).__name__}: {e}")
            continue

        # ✅ Використовуємо is_entry_recent замість is_entry_today
        new_entries = [
            e for e in feed.entries
            if e.link not in processed_urls
            and is_entry_recent(e)
            and is_rss_title_relevant(getattr(e, 'title', ''))
        ]
        print(f"   Нових (за 2 дні): {len(new_entries)}")

        for entry in new_entries[:5]:
            data = main.fetch_article_data(entry.link)
            
            # 💡 ГЛОБАЛЬНЕ РІШЕННЯ: Якщо сайт заблокував доступ, беремо опис з RSS
            if not data or not data.get('text'):
                summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
                clean_text = re.sub(r'<[^>]+>', ' ', summary_html).strip()
                
                if len(clean_text) > 30:
                    print(f"⚠️ Текст закрито захистом. Беремо опис з RSS: {entry.link[:60]}")
                    
                    # 🖼️ Шукаємо картинку всередині RSS-стрічки
                    rss_image = None
                    if hasattr(entry, 'media_content') and entry.media_content:
                        rss_image = entry.media_content[0].get('url')
                    elif hasattr(entry, 'enclosures') and entry.enclosures:
                        for enc in entry.enclosures:
                            if enc.get('type', '').startswith('image/'):
                                rss_image = enc.get('href')
                                break
                    if not rss_image and summary_html:
                        img_match = re.search(r'<img[^>]+src="([^">]+)"', summary_html)
                        if img_match:
                            rss_image = img_match.group(1)

                    data = {
                        "text": clean_text,
                        "title": entry.title,
                        "image": rss_image
                    }

            if data and data.get('text'):
                print(f"🆕 RSS: {entry.title[:60]}")
                process_and_send(data, entry.link, processed_urls)
            else:
                print(f"⏭️ Не вдалось отримати текст взагалі — пропускаємо: {entry.link[:60]}")
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
    
    # 20:00 UTC = 22:00 Київ — Вечірнє побажання
    schedule.every().day.at("20:00").do(send_evening_message)
    
    # Новини щогодини (нічний фільтр заблокує парсинг з 22:00 до 10:00)
    schedule.every(60).minutes.do(run_news_scout)

    print("🔍 Перший запуск парсингу при старті...")
    run_news_scout()

    print("📅 Дайджест о 10:00, новини щогодини, вечірнє побажання о 22:00.")

    while True:
        schedule.run_pending()
        time.sleep(30)
