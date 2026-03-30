import feedparser
import os
import time
import pytz
import schedule
import email.utils
import random
import re
import urllib.request
import json as _json
from datetime import datetime, timedelta
import main
import brain
import telegram_bot
import morning_digest
import weekly_digest          # 🆕 Тижневий дайджест

DB_FILE            = "parsed_urls.txt"
DIGEST_DATE_FILE   = "last_digest_date.txt"
EVENING_DATE_FILE  = "last_evening_date.txt"
MORNING_SCOUT_FILE = "last_morning_scout.txt"
WEEKLY_DATE_FILE   = "last_weekly_digest.txt"   # 🆕 Маркер тижневого дайджесту
KYIV_TZ            = pytz.timezone("Europe/Kiev")

# ── REDIS (Upstash) ───────────────────────────────────────────────────────────
REDIS_URL   = os.getenv("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")
REDIS_KEY   = "parsed_urls"

def _redis(cmd_parts):
    if not REDIS_URL or not REDIS_TOKEN:
        return None
    url  = REDIS_URL.rstrip("/")
    data = _json.dumps(cmd_parts).encode('utf-8')
    req  = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {REDIS_TOKEN}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return _json.loads(r.read())
    except Exception as e:
        print(f"⚠️ Redis помилка: {e}")
        return None
# ─────────────────────────────────────────────────────────────────────────────

def load_sources():
    if not os.path.exists("sources.txt"):
        return ["https://ain.ua/feed/"]
    with open("sources.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

RSS_SOURCES = load_sources()

def load_processed_urls():
    result = _redis(["SMEMBERS", REDIS_KEY])
    if result and "result" in result:
        urls = set(result["result"])
        print(f"✅ Redis: завантажено {len(urls)} URL з постійної пам'яті")
        return urls
    print("⚠️ Redis недоступний — використовую parsed_urls.txt як резерв")
    if not os.path.exists(DB_FILE):
        return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_processed_url(url):
    _redis(["SADD", REDIS_KEY, url])
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def cleanup_old_urls(max_lines=2000):
    pass

# ── 🆕 СЕМАНТИЧНИЙ ФІЛЬТР ДУБЛІКАТІВ ЗАГОЛОВКІВ (REDIS) ──────────────────────
def get_normalized_title(title):
    """Створює 'відбиток' заголовка: нижній регістр, тільки літери і цифри, 50 символів."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r'[^\w\sа-яёіїєґ]', '', t)   # прибираємо розділові знаки
    t = re.sub(r'\s+', '', t)               # прибираємо зайві пробіли повністю для щільного ключа
    return t[:50]

def is_title_duplicate(title):
    """Перевіряє, чи є такий відбиток у Redis."""
    fingerprint = get_normalized_title(title)
    if not fingerprint:
        return False
    key = f"title:{fingerprint}"
    result = _redis(["GET", key])
    # Якщо результат є і він не None, значить такий заголовок вже був
    if result and result.get("result") is not None:
        return True
    return False

def save_title_fingerprint(title):
    """Зберігає відбиток у Redis на 7 днів (604800 секунд)."""
    fingerprint = get_normalized_title(title)
    if fingerprint:
        key = f"title:{fingerprint}"
        _redis(["SET", key, "1", "EX", "604800"])
# ─────────────────────────────────────────────────────────────────────────────

# ── КОНТРОЛЕРИ ЧАСУ (КИЇВ) ТА ЗАВДАНЬ ────────────────────────────────────────
def was_task_done_today(filename):
    if not os.path.exists(filename):
        return False
    with open(filename, "r") as f:
        return f.read().strip() == get_today_kyiv()

def was_weekly_done_this_week(filename):
    if not os.path.exists(filename):
        return False
    now = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    current_week = now.strftime("%Y-W%W")   # наприклад "2026-W13"
    with open(filename, "r") as f:
        return f.read().strip() == current_week

def mark_weekly_done(filename):
    now = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    with open(filename, "w") as f:
        f.write(now.strftime("%Y-W%W"))

def mark_task_done(filename):
    with open(filename, "w") as f:
        f.write(get_today_kyiv())

def check_scheduled_tasks():
    now = datetime.now(pytz.utc).astimezone(KYIV_TZ)

    if now.hour == 10 and now.minute >= 0 and not was_task_done_today(DIGEST_DATE_FILE):
        send_morning_digest()
        return

    if (now.hour > 10 or (now.hour == 10 and now.minute >= 30)) \
            and not was_task_done_today(MORNING_SCOUT_FILE):
        if now.hour < 22:
            print("\n⏰ Час для першої порції новин (10:30+ за Києвом)")
            mark_task_done(MORNING_SCOUT_FILE)
            run_news_scout()
            return

    if now.weekday() == 6 and now.hour == 21 and now.minute >= 45 \
            and not was_weekly_done_this_week(WEEKLY_DATE_FILE):
        send_weekly_digest()
        return

    if now.hour == 22 and now.minute >= 0 and not was_task_done_today(EVENING_DATE_FILE):
        send_evening_message()
        return
# ─────────────────────────────────────────────────────────────────────────────

def get_today_kyiv():
    return datetime.now(pytz.utc).astimezone(KYIV_TZ).strftime("%Y-%m-%d")

RSS_STOP_WORDS_EXACT = [
    "мотоцикл", "мото", "скутер", "квадроцикл",
    "вантажівк", "тягач", "автобус", "тролейбус",
    "трактор", "комбайн", "причіп", "фура",
    "motorcycle", "motorbike", "scooter",
    "pickup truck", "semi truck", "big rig",
]

RSS_STOP_WORDS_WHOLE = [
    r"\btruck\b",
    r"\bbus\b",
    r"\bcoach\b",
    r"\btractor\b",
    r"\btrailer\b",
]

def is_rss_title_relevant(title):
    title_lower = title.lower()
    for word in RSS_STOP_WORDS_EXACT:
        if word in title_lower:
            print(f"🚫 RSS стоп-слово '{word}': {title[:60]}")
            return False
    for pattern in RSS_STOP_WORDS_WHOLE:
        if re.search(pattern, title_lower):
            print(f"🚫 RSS стоп-слово (regex) '{pattern}': {title[:60]}")
            return False
    return True

def is_entry_recent(entry):
    now = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    allowed_dates = [
        now.strftime("%Y-%m-%d"),
        (now - timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    published_str = getattr(entry, "published", "")
    if published_str:
        try:
            dt = email.utils.parsedate_to_datetime(published_str)
            entry_date = dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
            return entry_date in allowed_dates
        except Exception:
            pass
    published = getattr(entry, "published_parsed", None)
    if not published:
        return True
    try:
        entry_dt   = datetime(*published[:6], tzinfo=pytz.utc)
        entry_date = entry_dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d")
        return entry_date in allowed_dates
    except Exception:
        return True

def smart_sleep(seconds):
    end_time = time.time() + seconds
    while time.time() < end_time:
        if datetime.now(pytz.utc).astimezone(KYIV_TZ).hour >= 22:
            print("⏰ Настав час сну (22:00+). Перериваємо паузу!")
            return False
        time.sleep(5)
    return True

def process_and_send(data, url, processed_urls):
    raw_summary = brain.summarize_text(data['text'], data['title'])

    if "[TITLE]:" in raw_summary:
        parts     = raw_summary.split("[TITLE]:", 1)[1].split("\n", 1)
        ua_title  = parts[0].strip()
        final_msg = f"⚡️ <b>{ua_title.upper()}</b>\n\n{parts[1].strip()}"
    else:
        ua_title  = data['title']
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
        print(f"✅ Збережено в хмарну базу: {url[:60]}...")

        # 🆕 Зберігаємо 'відбиток' оригінального англійського заголовка в Redis на 7 днів
        save_title_fingerprint(data.get('title', ''))

        weekly_digest.add_headline_to_weekly(ua_title, url)

        pause_seconds = random.randint(300, 420)
        print(f"⏳ Чекаю {pause_seconds // 60} хв {pause_seconds % 60} сек перед наступним постом...")

        if not smart_sleep(pause_seconds):
            return False
    else:
        print(f"⚠️ Не відправлено — спробуємо наступного разу.")

    return True

def send_morning_digest():
    if was_task_done_today(DIGEST_DATE_FILE):
        print("⏭️ Дайджест сьогодні вже відправлявся.")
        return
    print("\n🌅 Відправляю ранковий дайджест...")
    try:
        digest_msg = morning_digest.build_morning_digest()
        success    = telegram_bot.send_telegram_message(text=digest_msg)
        if success:
            mark_task_done(DIGEST_DATE_FILE)
            print("✅ Дайджест відправлено!")
    except Exception as e:
        print(f"❌ Помилка дайджесту: {type(e).__name__}: {e}")

def send_weekly_digest():
    if was_weekly_done_this_week(WEEKLY_DATE_FILE):
        print("⏭️ Тижневий дайджест цього тижня вже відправлявся.")
        return
    print("\n📊 Відправляю тижневий дайджест...")
    try:
        success = weekly_digest.send_weekly_digest()
        if success:
            mark_weekly_done(WEEKLY_DATE_FILE)
            print("✅ Тижневий дайджест відправлено!")
    except Exception as e:
        print(f"❌ Помилка тижневого дайджесту: {type(e).__name__}: {e}")

def send_evening_message():
    if was_task_done_today(EVENING_DATE_FILE):
        print("⏭️ Вечірнє повідомлення сьогодні вже відправлялось.")
        return

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
        ai_text = re.sub(r'[*_`]', '', ai_text)

        final_msg = f"🌙 <b>НА ДОБРАНІЧ</b>\n\n{ai_text}\n\n✨ <i>Ваш Агент Софія</i>"
        social_links = (
            "\n\n📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
            "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
            "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
            "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
        )
        final_msg += social_links

        success = telegram_bot.send_telegram_message(text=final_msg)
        if success:
            mark_task_done(EVENING_DATE_FILE)
            print("✅ Вечірнє повідомлення відправлено!")
    except Exception as e:
        print(f"❌ Помилка вечірнього повідомлення: {e}")

def run_news_scout():
    now = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    if now.hour >= 22 or now.hour < 10 or (now.hour == 10 and now.minute < 30):
        print(f"😴 Нічний режим або очікування 10:30 ({now.strftime('%H:%M')}). Парсинг зупинено.")
        return

    today          = get_today_kyiv()
    processed_urls = load_processed_urls()
    cleanup_old_urls()

    print(f"\n🔍 Парсинг новин за {today} (включаючи вчорашні нічні)")
    print(f"📋 RSS джерел: {len(RSS_SOURCES)}")

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

        new_entries = [
            e for e in feed.entries
            if e.link not in processed_urls
            and is_entry_recent(e)
            and is_rss_title_relevant(getattr(e, 'title', ''))
        ]
        print(f"   Нових (за 2 дні): {len(new_entries)}")

        for entry in new_entries[:5]:
            
            # 🆕 ПЕРЕВІРКА НА ДУБЛІКАТ ДО ТОГО, ЯК ЙТИ НА САЙТ ТА У GEMINI
            if is_title_duplicate(getattr(entry, 'title', '')):
                print(f"⏭️ Дублікат по семантиці (пропускаємо): {entry.title[:60]}")
                save_processed_url(entry.link)
                processed_urls.add(entry.link)
                continue
            
            data = main.fetch_article_data(entry.link)

            if not data or not data.get('text'):
                summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
                clean_text   = re.sub(r'<[^>]+>', ' ', summary_html).strip()

                if len(clean_text) > 30:
                    print(f"⚠️ Текст закрито захистом. Беремо опис з RSS: {entry.link[:60]}")

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

                    data = {"text": clean_text, "title": entry.title, "image": rss_image}

            if data and data.get('text'):
                print(f"🆕 RSS: {entry.title[:60]}")
                if not process_and_send(data, entry.link, processed_urls):
                    return
            else:
                print(f"⏭️ Не вдалось отримати текст — пропускаємо: {entry.link[:60]}")
                save_processed_url(entry.link)
                processed_urls.add(entry.link)

if __name__ == "__main__":
    import web_server

    print("🌐 Запускаю фоновий веб-сервер...")
    web_server.keep_alive()

    print("🚀 CyberWheel стартував з хмарною пам'яттю!")

    print("🔎 Перевірка пропущених завдань після старту...")
    check_scheduled_tasks()

    # Запускаємо контролер кожні 5 хвилин
    schedule.every(5).minutes.do(check_scheduled_tasks)

    # Регулярний парсинг новин щогодини
    schedule.every(60).minutes.do(run_news_scout)

    print("📅 Розклад: дайджест 10:00 | новини щогодини | тижневий 21:45 нед | добраніч 22:00")

    while True:
        schedule.run_pending()
        time.sleep(30)
