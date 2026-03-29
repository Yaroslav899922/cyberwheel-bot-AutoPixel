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
MAX_STORED  = 100                  # Максимум записів у списку (≈3 тижні)

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

    # Нормалізуємо заголовок: прибираємо HTML-теги та зайві пробіли
    clean_title = re.sub(r"<[^>]+>", "", title).strip()
    # Обрізаємо до 80 символів — достатньо для Gemini і компактно в Redis
    clean_title = clean_title[:80]

    entry = f"{clean_title}||{url}"

    # Додаємо в кінець списку
    _redis(["RPUSH", WEEKLY_KEY, entry])

    # Обрізаємо до MAX_STORED записів (зберігаємо тільки останні 100)
    _redis(["LTRIM", WEEKLY_KEY, -MAX_STORED, -1])

    print(f"📝 [WeeklyDigest] Збережено заголовок: {clean_title[:50]}...")

# ── ДІАПАЗОН ДАТ ──────────────────────────────────────────────────────────────
def get_week_range_label() -> str:
    """
    Повертає рядок діапазону дат для заголовку дайджесту.
    Приклади:
      "23–29 березня"
      "28 березня – 3 квітня"
    """
    now   = datetime.now(pytz.utc).astimezone(KYIV_TZ)
    end   = now
    start = now - timedelta(days=6)

    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_UA[end.month]}"
    else:
        return f"{start.day} {MONTHS_UA[start.month]} – {end.day} {MONTHS_UA[end.month]}"

# ── ОТРИМАННЯ ЗАГОЛОВКІВ З REDIS ──────────────────────────────────────────────
def get_weekly_headlines() -> list[dict]:
    """
    Повертає список словників: [{"title": ..., "url": ...}, ...]
    Бере всі записи з Redis LIST weekly_headlines.
    """
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

# ── GEMINI: ВИБІР ТОП-5 ───────────────────────────────────────────────────────
def pick_top5_with_gemini(headlines: list[dict]) -> list[dict] | None:
    """
    Передає список заголовків у Gemini.
    Gemini повертає JSON з топ-5 індексами та коротким поясненням.
    Повертає список з 5 словників: [{"title": ..., "url": ..., "why": ...}, ...]
    """
    if not headlines:
        return None

    # Формуємо нумерований список для промпту
    numbered = "\n".join(
        f"{i+1}. {h['title']}" for i, h in enumerate(headlines)
    )

    prompt = f"""Ти — Агент Софія, аналітик автомобільного каналу Skoda_Kremen_News.
Ось список заголовків новин за тиждень:

{numbered}

ЗАВДАННЯ:
Обери рівно 5 найважливіших новин для аудиторії українського автосалону Škoda.

ПРІОРИТЕТИ при виборі (в порядку важливості):
1. Новини про бренд Škoda або моделі Fabia, Scala, Octavia, Superb, Kamiq, Karoq, Kodiaq, Enyaq
2. Тренди електромобілів та нових технологій
3. Значні події автомобільного ринку (продажі, рейтинги, закони)
4. Цікаві новинки від ключових конкурентів

ФОРМАТ ВІДПОВІДІ — ТІЛЬКИ ВАЛІДНИЙ JSON, БЕЗ ЗАЙВИХ СЛІВ:
[
  {{"index": 3, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 7, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 1, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 12, "why": "коротко чому важливо — 1 речення"}},
  {{"index": 5, "why": "коротко чому важливо — 1 речення"}}
]

ПРАВИЛА:
- index — це номер з наведеного списку (починається з 1)
- "why" — просте речення БЕЗ канцеляризмів та пафосу
- Якщо є новини про Škoda — вони ОБОВ'ЯЗКОВО в списку
- Рівно 5 елементів, не більше і не менше
"""

    # ✅ Той самий fallback що і в brain.py
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

            # Прибираємо можливі markdown-огорожі
            raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")

            top5_indices = _json.loads(raw)

            result = []
            for item in top5_indices:
                idx = item.get("index", 0) - 1  # перетворюємо на 0-based
                if 0 <= idx < len(headlines):
                    result.append({
                        "title": headlines[idx]["title"],
                        "url":   headlines[idx]["url"],
                        "why":   item.get("why", "").strip()
                    })

            if len(result) == 5:
                print(f"✅ [WeeklyDigest] Модель {m} обрала топ-5 успішно.")
                return result
            else:
                print(f"⚠️ [WeeklyDigest] Модель {m} повернула {len(result)} замість 5.")
                continue

        except Exception as e:
            print(f"⚠️ [WeeklyDigest] Модель {m} не відповіла: {e}")
            continue

    print("❌ [WeeklyDigest] Всі моделі недоступні.")
    return None

# ── GEMINI: ВЕРДИКТ ───────────────────────────────────────────────────────────
def get_weekly_verdict(top5: list[dict]) -> str:
    """
    Генерує загальний висновок Агента Софії про тиждень.
    Простою мовою, без заумних слів.
    """
    titles_str = "\n".join(f"- {item['title']}" for item in top5)

    prompt = f"""Ти — Агент Софія, аналітик автомобільного каналу Skoda_Kremen_News.
Пиши від жіночого роду ("я проаналізувала", "вважаю").

Ось 5 головних автоновин цього тижня:
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

    # ✅ Той самий fallback що і в brain.py
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

# ── ЗБІРКА ПОВІДОМЛЕННЯ ───────────────────────────────────────────────────────
def build_weekly_digest_message() -> str | None:
    """
    Головна функція: збирає та повертає готове HTML-повідомлення для Telegram.
    Повертає None якщо недостатньо даних.
    """
    headlines = get_weekly_headlines()

    if len(headlines) < 5:
        print(f"⚠️ [WeeklyDigest] Замало заголовків ({len(headlines)}) — потрібно мінімум 5.")
        return None

    top5 = pick_top5_with_gemini(headlines)
    if not top5:
        print("❌ [WeeklyDigest] Gemini не зміг обрати топ-5.")
        return None

    verdict  = get_weekly_verdict(top5)
    date_range = get_week_range_label()

    EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    # Формуємо список новин
    news_lines = []
    for i, item in enumerate(top5):
        title = item["title"]
        url   = item["url"]
        why   = item["why"]

        # Назва статті як посилання (якщо є url)
        if url:
            title_html = f'<a href="{url}">{title}</a>'
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
        f"🏆 <b>ТОП-5 НОВИН ТИЖНЯ</b>\n"
        f"<i>Агент Софія підготувала головне за {date_range}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{news_block}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Вердикт Агента Софії:</b>\n"
        f"<blockquote expandable>{verdict}</blockquote>\n\n"
        f"✨ <i>Ваш Агент Софія</i>\n\n"
        f"{social_links}"
    )

    # Після відправки — очищаємо список для наступного тижня
    _redis(["DEL", WEEKLY_KEY])
    print(f"🗑️ [WeeklyDigest] Redis-список {WEEKLY_KEY} очищено для наступного тижня.")

    return message

# ── ВІДПРАВКА ─────────────────────────────────────────────────────────────────
def send_weekly_digest() -> bool:
    """
    Збирає і відправляє тижневий дайджест у Telegram.
    Повертає True при успіху.
    """
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

    # Тест діапазону дат
    print(f"📅 Діапазон: {get_week_range_label()}\n")

    # Тест з тестовими даними
    test_headlines = [
        {"title": "Škoda Kodiaq 2025 отримав новий двигун", "url": "https://example.com/1"},
        {"title": "Електромобілі в Україні: продажі зросли на 40%", "url": "https://example.com/2"},
        {"title": "Toyota представила новий Camry", "url": "https://example.com/3"},
        {"title": "Tesla знизила ціни в Європі", "url": "https://example.com/4"},
        {"title": "Нові правила розмитнення авто в Україні", "url": "https://example.com/5"},
        {"title": "Škoda Enyaq оновив запас ходу до 600 км", "url": "https://example.com/6"},
        {"title": "BMW представила електричний M3", "url": "https://example.com/7"},
    ]

    print(f"📋 Тестових заголовків: {len(test_headlines)}")
    top5 = pick_top5_with_gemini(test_headlines)

    if top5:
        print("\n🏆 Топ-5 від Gemini:")
        for i, item in enumerate(top5, 1):
            print(f"  {i}. {item['title']}")
            print(f"     → {item['why']}")

        verdict = get_weekly_verdict(top5)
        print(f"\n💬 Вердикт:\n{verdict}")
    else:
        print("❌ Gemini не відповів")
