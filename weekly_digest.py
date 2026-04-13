import os
import re
import pytz
import urllib.request
import json as _json
from datetime import datetime, timedelta

# ── ЗАЛЕЖНОСТІ (ті самі що в auto_parser.py) ─────────────────────────────────
import brain
import telegram_bot

KYIV_TZ     = pytz.timezone("Europe/Kiev")
REDIS_URL   = os.getenv("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

WEEKLY_KEY  = "weekly_headlines"   # Redis LIST: "заголовок||url"
MAX_STORED  = 200                  # Збільшено: ~4 тижні при активній роботі

MONTHS_UA = {
    1: "січня",   2: "лютого",  3: "березня",  4: "квітня",
    5: "травня",  6: "червня",  7: "липня",     8: "серпня",
    9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня"
}

# ── REDIS HELPER ──────────────────────────────────────────────────────────────
def _redis(cmd_parts):
    """Той самий Redis-хелпер що і в auto_parser.py"""
    if not REDIS_URL or not REDIS_TOKEN:
        return None
    url  = REDIS_URL.rstrip("/")
    data = _json.dumps(cmd_parts).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {REDIS_TOKEN}",
            "Content-Type":  "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return _json.loads(r.read())
    except Exception as e:
        print(f"⚠️ [WeeklyDigest] Redis помилка: {e}")
        return None

# ── ЗАПИС ЗАГОЛОВКУ ПРИ КОЖНІЙ ПУБЛІКАЦІЇ ────────────────────────────────────
def add_headline_to_weekly(title: str, url: str):
    """
    Викликається з auto_parser.py → process_and_send() після успішної публікації.
    Зберігає: "заголовок||url" у Redis LIST weekly_headlines.
    """
    if not title or not url:
        return

    clean_title = re.sub(r"<[^>]+>", "", title).strip()
    clean_title = clean_title[:80]

    entry = f"{clean_title}||{url}"

    _redis(["RPUSH", WEEKLY_KEY, entry])
    _redis(["LTRIM", WEEKLY_KEY, -MAX_STORED, -1])

    print(f"📝 [WeeklyDigest] Збережено заголовок: {clean_title[:50]}...")

# ── СИСТЕМА ПРІОРИТЕТІВ ───────────────────────────────────────────────────────
#
# Заголовки зберігаються УКРАЇНСЬКОЮ (ua_title після перекладу Gemini).
#
# Пріоритети (погоджено):
#   +10  Škoda / моделі Škoda — завжди в дайджест якщо є
#   +10  Ринок/продажі/статистика УКРАЇНИ — рівень Škoda, обов'язково
#   +5   Електромобілі / нові технології
#   +4   Рекорди / прориви
#   +3   Ринок/продажі/статистика (не Україна)
#   +2   Ціни/акції УКРАЇНИ
#   -1   Ціни/акції НЕ України — виключаємо з дайджесту повністю
# ─────────────────────────────────────────────────────────────────────────────

UKRAINE_KEYWORDS = ["україн", "вітчизн", "київ", "українськ"]

SKODA_KEYWORDS = [
    "škoda", "skoda", "шкода",
    "fabia", "фабія", "scala", "скала",
    "octavia", "октавія", "superb", "суперб",
    "kamiq", "камік", "karoq", "карок",
    "kodiaq", "кодіак", "enyaq", "еняк",
]

EV_KEYWORDS = [
    "електр", "гібрид", "hybrid", "батаре",
    "заряд", "технолог", "безпілот", "автопілот",
]

RECORD_KEYWORDS = [
    "рекорд", "найшвидш", "перший", "вперше",
    "прорив", "рекордн", "світовий",
]

MARKET_KEYWORDS = [
    "продаж", "ринок", "статистик", "рейтинг",
    "закон", "правил", "реєстрац", "імпорт",
]

PRICE_KEYWORDS = [
    "цін", "знижк", "акці", "дешевш",
    "знизи", "підвищи", "вартіст", "ціноутворен",
]


def score_headline(title: str) -> int:
    """
    Повертає числовий пріоритет заголовку за погодженою системою балів.
    Повертає -1 для статей які потрібно повністю виключити з дайджесту.
    """
    t = title.lower()

    is_ukraine = any(kw in t for kw in UKRAINE_KEYWORDS)
    is_skoda   = any(kw in t for kw in SKODA_KEYWORDS)
    is_price   = any(kw in t for kw in PRICE_KEYWORDS)
    is_market  = any(kw in t for kw in MARKET_KEYWORDS)

    # Ціни/акції не про Україну і не про Škoda — виключаємо повністю
    if is_price and not is_ukraine and not is_skoda:
        return -1

    score = 0

    # Škoda → +10
    if is_skoda:
        score += 10

    # Ринок України → +10 (рівень Škoda, обов'язково)
    if is_ukraine and is_market:
        score += 10

    # Електро / технології → +5
    if any(kw in t for kw in EV_KEYWORDS):
        score += 5

    # Рекорди / прориви → +4
    if any(kw in t for kw in RECORD_KEYWORDS):
        score += 4

    # Ринок/продажі (не Україна) → +3
    if is_market:
        score += 3

    # Ціни/акції України → +2
    if is_price and is_ukraine:
        score += 2

    return score


def deduplicate_headlines(headlines: list[dict]) -> list[dict]:
    """
    Прибирає дублікати тем зі списку тижневих заголовків.
    Якщо два заголовки мають ≥3 спільних значущих слова — залишає перший.
    """
    accepted = []
    accepted_word_sets = []

    for h in headlines:
        words = {
            w for w in re.sub(r'[^\w\s]', ' ', h['title'].lower()).split()
            if len(w) > 3
        }

        is_dup = False
        for existing_words in accepted_word_sets:
            if len(words & existing_words) >= 3:
                is_dup = True
                break

        if not is_dup:
            accepted.append(h)
            accepted_word_sets.append(words)

    print(f"🔍 [WeeklyDigest] Після дедублікації: {len(accepted)} з {len(headlines)}")
    return accepted


def prefilter_headlines(headlines: list[dict]) -> list[dict]:
    """
    Підготовка списку для Gemini:
    1. Прибираємо дублікати тем
    2. Виставляємо бали за пріоритетами
    3. Виключаємо статті з балом -1 (ціни не-України)
    4. Повертаємо топ-30 за балами — саме їх отримає Gemini
    """
    # Крок 1: дедублікація
    unique = deduplicate_headlines(headlines)

    # Крок 2: оцінка + фільтрація виключень
    scored = []
    excluded = 0
    for h in unique:
        s = score_headline(h['title'])
        if s == -1:
            excluded += 1
            continue
        scored.append((s, h))

    print(f"🚫 [WeeklyDigest] Виключено нерелевантних (ціни не-України): {excluded}")

    # Крок 3: сортуємо за балами — найважливіші першими
    scored.sort(key=lambda x: x[0], reverse=True)

    # Крок 4: беремо топ-30
    top30 = [h for _, h in scored[:30]]

    print(f"📊 [WeeklyDigest] Передаємо Gemini топ-{len(top30)} (з {len(unique)} унікальних)")

    # Показуємо розподіл балів для діагностики
    for score, h in scored[:10]:
        print(f"   [{score:+d}] {h['title'][:60]}")

    return top30


# ── GEMINI: ВИБІР ТОП-7 ───────────────────────────────────────────────────────
def pick_top7_with_gemini(headlines: list[dict]) -> list[dict] | None:
    """
    Передає попередньо відфільтрований список у Gemini.
    Gemini робить фінальний вибір з топ-30 і повертає 7 найкращих.
    """
    if not headlines:
        return None

    numbered = "\n".join(
        f"{i+1}. {h['title']}" for i, h in enumerate(headlines)
    )

    prompt = f"""Ти — Агент Софія, аналітик автомобільного каналу Skoda_Kremen_News.
Ось попередньо відібрані найважливіші новини тижня:

{numbered}

ЗАВДАННЯ:
Обери рівно 7 найважливіших новин для аудиторії українського автосалону Škoda.

ПРІОРИТЕТИ при виборі (суворо в порядку важливості):
1. Новини про бренд Škoda або моделі Fabia, Scala, Octavia, Superb, Kamiq, Karoq, Kodiaq, Enyaq — ОБОВ'ЯЗКОВО якщо є
2. Новини про автомобільний ринок України (продажі, закони, статистика) — ОБОВ'ЯЗКОВО якщо є, це рівень Škoda
3. Тренди електромобілів та нових технологій
4. Рекорди та значні технічні досягнення
5. Важливі події світового авторинку

ДОДАТКОВІ ПРАВИЛА:
- Забезпечи різноманітність — не більше 2 новин однієї категорії
- НЕ обирай ціни/акції якщо вони не стосуються України або Škoda
- Перевага новинам які будуть цікаві покупцям авто в Україні

ФОРМАТ ВІДПОВІДІ — ТІЛЬКИ ВАЛІДНИЙ JSON, БЕЗ ЗАЙВИХ СЛІВ:
[
  {{"index": 3, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 7, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 1, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 12, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 5, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 9, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 2, "why": "коротко чому важливо — 1 речення"}}
]

ПРАВИЛА ФОРМАТУ:
- index — це номер з наведеного списку (починається з 1)
- "why" — просте речення БЕЗ канцеляризмів та пафосу
- Рівно 7 елементів, не більше і не менше
"""

    models = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest"
    ]

    for m in models:
        try:
            response = brain.client.models.generate_content(
                model=m,
                contents=prompt
            )
            raw = response.text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")

            top7_indices = _json.loads(raw)

            result = []
            for item in top7_indices:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(headlines):
                    result.append({
                        "title": headlines[idx]["title"],
                        "url":   headlines[idx]["url"],
                        "why":   item.get("why", "").strip()
                    })

            if len(result) == 7:
                print(f"✅ [WeeklyDigest] Модель {m} обрала топ-7 успішно.")
                return result
            else:
                print(f"⚠️ [WeeklyDigest] Модель {m} повернула {len(result)} замість 7.")
                continue

        except Exception as e:
            print(f"⚠️ [WeeklyDigest] Модель {m} не відповіла: {e}")
            continue

    print("❌ [WeeklyDigest] Всі моделі недоступні.")
    return None


# ── GEMINI: ВЕРДИКТ ───────────────────────────────────────────────────────────
def get_weekly_verdict(top7: list[dict]) -> str:
    """
    Генерує загальний висновок Агента Софії про тиждень на основі топ-7.
    """
    titles_str = "\n".join(f"- {item['title']}" for item in top7)

    prompt = f"""Ти — Агент Софія, аналітик автомобільного каналу Skoda_Kremen_News.
Пиши від жіночого роду ("я проаналізувала", "вважаю").

Ось 7 головних автоновин цього тижня:
{titles_str}

ЗАВДАННЯ: Напиши короткий загальний висновок про тиждень (2-3 речення).

ПРАВИЛА:
- Простою живою мовою, без канцеляризмів
- НЕ повторюй факти зі списку — дай своє бачення тенденцій
- НЕ вживай: "надзвичайно", "неймовірно", "фантастично", "варто зазначити"
- Якщо є тренд (наприклад, кілька новин про електро) — назви його
- 2-3 речення максимум
- ТІЛЬКИ текст вердикту, без заголовків та підписів
"""

    models = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest"
    ]

    for m in models:
        try:
            response = brain.client.models.generate_content(
                model=m,
                contents=prompt
            )
            verdict = response.text.strip()
            verdict = re.sub(r"[*_`]", "", verdict)
            print(f"✅ [WeeklyDigest] Вердикт від моделі {m}.")
            return verdict
        except Exception as e:
            print(f"⚠️ [WeeklyDigest] Модель {m} не відповіла для вердикту: {e}")
            continue

    return "Цього тижня автосвіт не стояв на місці — попереду ще цікавіше."


# ── ДІАПАЗОН ДАТ ──────────────────────────────────────────────────────────────
def get_week_range_label() -> str:
    now   = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    end   = now
    start = now - timedelta(days=6)

    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_UA[end.month]}"
    else:
        return f"{start.day} {MONTHS_UA[start.month]} – {end.day} {MONTHS_UA[end.month]}"


# ── ОТРИМАННЯ ЗАГОЛОВКІВ З REDIS ──────────────────────────────────────────────
def get_weekly_headlines() -> list[dict]:
    result = _redis(["LRANGE", WEEKLY_KEY, "0", "-1"])
    if not result or "result" not in result:
        print("⚠️ [WeeklyDigest] Redis недоступний або список порожній.")
        return []

    headlines = []
    for entry in result["result"]:
        if "||" in entry:
            parts = entry.split("||", 1)
            headlines.append({"title": parts[0].strip(), "url": parts[1].strip()})
        else:
            headlines.append({"title": entry.strip(), "url": ""})

    print(f"📋 [WeeklyDigest] Знайдено заголовків: {len(headlines)}")
    return headlines


# ── ЗБІРКА ПОВІДОМЛЕННЯ ───────────────────────────────────────────────────────
def build_weekly_digest_message() -> str | None:
    """
    Головна функція: збирає та повертає готове HTML-повідомлення для Telegram.
    Повертає None якщо недостатньо даних.
    """
    headlines = get_weekly_headlines()

    if len(headlines) < 7:
        print(f"⚠️ [WeeklyDigest] Замало заголовків ({len(headlines)}) — потрібно мінімум 7.")
        return None

    # Передфільтрація: дедублікація + бали + топ-30 для Gemini
    filtered = prefilter_headlines(headlines)

    if len(filtered) < 7:
        print(f"⚠️ [WeeklyDigest] Після фільтрації залишилось {len(filtered)} — замало.")
        return None

    top7 = pick_top7_with_gemini(filtered)
    if not top7:
        print("❌ [WeeklyDigest] Gemini не зміг обрати топ-7.")
        return None

    verdict    = get_weekly_verdict(top7)
    date_range = get_week_range_label()

    EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]

    news_lines = []
    for i, item in enumerate(top7):
        title = item["title"]
        url   = item["url"]
        why   = item["why"]

        if url:
            title_html = f'<b><a href="{url}">{title}</a></b>'
        else:
            title_html = f"<b>{title}</b>"

        news_lines.append(f"{EMOJIS[i]} {title_html}\n<i>{why}</i>")

    news_block = "\n\n".join(news_lines)

    social_links = (
        "📷 <a href='https://www.instagram.com/avtocenter_skoda/'>Instagram</a>  |  "
        "🎵 <a href='https://www.tiktok.com/@skoda_kremen'>TikTok</a>  |  "
        "📘 <a href='https://www.facebook.com/skodakremen'>Facebook</a>  |  "
        "🌐 <a href='https://www.avtocenter-kremenchuk.site/'>Наш сайт</a>"
    )

    message = (
        f"🏆 <b>ТОП-7 НОВИН ТИЖНЯ</b>\n"
        f"<i>Агент Софія підготувала головне за {date_range}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{news_block}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Вердикт Агента Софії:</b>\n"
        f"<blockquote expandable>{verdict}</blockquote>\n\n"
        f"✨ <i>Ваш Агент Софія</i>\n\n"
        f"{social_links}"
    )

    # Після збірки — очищаємо список для наступного тижня
    _redis(["DEL", WEEKLY_KEY])
    print(f"🗑️ [WeeklyDigest] Redis-список {WEEKLY_KEY} очищено для наступного тижня.")

    return message


# ── ВІДПРАВКА ─────────────────────────────────────────────────────────────────
def send_weekly_digest() -> bool:
    print("\n📊 Збираю тижневий дайджест...")
    message = build_weekly_digest_message()

    if not message:
        print("⚠️ [WeeklyDigest] Повідомлення не сформовано — пропускаємо.")
        return False

    success = telegram_bot.send_telegram_message(text=message)

    if success:
        print("✅ [WeeklyDigest] Тижневий дайджест відправлено!")
    else:
        print("❌ [WeeklyDigest] Помилка відправки тижневого дайджесту.")

    return success


# ── ТЕСТ ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🧪 Тестую weekly_digest.py...\n")

    print(f"📅 Діапазон: {get_week_range_label()}\n")

    test_headlines = [
        {"title": "Škoda Kodiaq 2025 отримав новий двигун", "url": "https://example.com/1"},
        {"title": "Електромобілі в Україні: продажі зросли на 40%", "url": "https://example.com/2"},
        {"title": "Toyota представила новий Camry", "url": "https://example.com/3"},
        {"title": "Tesla знизила ціни в Європі", "url": "https://example.com/4"},
        {"title": "Нові правила розмитнення авто в Україні", "url": "https://example.com/5"},
        {"title": "Škoda Enyaq оновив запас ходу до 600 км", "url": "https://example.com/6"},
        {"title": "BMW представила електричний M3", "url": "https://example.com/7"},
        {"title": "Ford GT встановив рекорд Нюрбургрингу", "url": "https://example.com/8"},
        {"title": "Honda знизила ціни на Prologue в США", "url": "https://example.com/9"},
        {"title": "Ринок електромобілів України: підсумки кварталу", "url": "https://example.com/10"},
    ]

    print("📊 Тест системи балів:")
    for h in test_headlines:
        s = score_headline(h['title'])
        marker = "🚫" if s == -1 else f"[{s:+d}]"
        print(f"  {marker} {h['title']}")

    print(f"\n📋 Тестових заголовків: {len(test_headlines)}")
    filtered = prefilter_headlines(test_headlines)

    top7 = pick_top7_with_gemini(filtered)

    if top7:
        print("\n🏆 Топ-7 від Gemini:")
        for i, item in enumerate(top7, 1):
            print(f"  {i}. {item['title']}")
            print(f"     → {item['why']}")

        verdict = get_weekly_verdict(top7)
        print(f"\n💬 Вердикт:\n{verdict}")
    else:
        print("❌ Gemini не відповів")
