import requests
import re
import os
from bs4 import BeautifulSoup

# -------------------------------------------------------
# Розділи які парсимо з autoconsulting.ua
# CARS    = ?part=CARS     (легкові авто)
# SALES   = ?part=SALES    (новини продажів %)
# catid=39 = Електромобілі
# -------------------------------------------------------
SECTIONS = [
    {"name": "CARS",          "url": "https://autoconsulting.ua/news.php?part=CARS"},
    {"name": "SALES",         "url": "https://autoconsulting.ua/news.php?part=SALES"},
    {"name": "Електромобілі", "url": "https://autoconsulting.ua/news.php?catid=39"},
]

BASE_URL = "https://autoconsulting.ua"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk,ru;q=0.9,en;q=0.8",
}

def fetch_page(url):
    """
    Завантажує сторінку та конвертує з windows-1251 у UTF-8.
    Це головна хитрість — без цього кроку весь текст буде кракозябрами.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        # Примусово вказуємо кодування — сайт не завжди відповідає з правильним charset
        response.encoding = "windows-1251"
        return response.text
    except Exception as e:
        print(f"❌ [AutoConsulting] Помилка завантаження {url}: {type(e).__name__}: {e}")
        return None

def get_article_links(section_url):
    """
    Витягує всі посилання на статті з однієї сторінки розділу.
    Повертає список URL виду: https://autoconsulting.ua/article.php?sid=XXXXX
    """
    html = fetch_page(section_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Шукаємо тільки посилання на статті (article.php?sid=...)
        if "article.php?sid=" in href:
            # Деякі посилання відносні, деякі абсолютні — нормалізуємо
            if href.startswith("http"):
                full_url = href
            else:
                full_url = BASE_URL + "/" + href.lstrip("/")
            if full_url not in links:
                links.append(full_url)

    return links

def fetch_article_text(article_url):
    """
    Завантажує текст конкретної статті autoconsulting.ua
    та повертає словник {text, title, image} — такий самий формат
    як у main.fetch_article_data(), щоб решта коду працювала без змін.
    """
    html = fetch_page(article_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # --- Заголовок ---
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        # Заголовок сторінки зазвичай: "Назва статті: новини на AUTO-Consulting - Бренд"
        raw_title = title_tag.get_text(strip=True)
        # Обрізаємо суфікс сайту
        title = raw_title.split(":")[0].strip() if ":" in raw_title else raw_title

    # --- Текст статті ---
    # Autoconsulting тримає текст у таблицях, шукаємо найбільший блок тексту
    text = ""
    best_td = None
    best_len = 0
    for td in soup.find_all("td"):
        td_text = td.get_text(separator=" ", strip=True)
        if len(td_text) > best_len:
            best_len = len(td_text)
            best_td = td

    if best_td:
        # Видаляємо навігаційні блоки (меню, реклама)
        for tag in best_td.find_all(["script", "style", "a"]):
            tag.decompose()
        text = best_td.get_text(separator="\n", strip=True)

    if not text or len(text) < 100:
        print(f"⚠️ [AutoConsulting] Текст не знайдено або занадто короткий: {article_url}")
        return None

    # --- Зображення ---
    image_url = None
    for img in soup.find_all("img", src=True):
        src = img["src"]
        # Шукаємо змістовні картинки (не банери та не іконки)
        if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png"]):
            if not any(skip in src.lower() for skip in ["adclick", "banner", "logo", "icon", "button"]):
                if src.startswith("http"):
                    image_url = src
                else:
                    image_url = BASE_URL + "/" + src.lstrip("/")
                break

    print(f"✅ [AutoConsulting] Завантажено: {title[:60]}...")
    return {
        "text": text,
        "title": title,
        "image": image_url
    }

def get_new_articles(processed_urls):
    """
    Головна функція — збирає нові статті з усіх розділів.
    Повертає список словників: [{url, data}, ...]
    Використовується з auto_parser.py замість feedparser.
    """
    new_articles = []

    for section in SECTIONS:
        print(f"\n📡 [AutoConsulting] Перевіряю розділ: {section['name']}")
        links = get_article_links(section["url"])
        print(f"   Знайдено посилань: {len(links)}")

        # Беремо тільки нові (не оброблені раніше)
        new_links = [l for l in links if l not in processed_urls]
        print(f"   Нових статей: {len(new_links)}")

        # Обмежуємо до 2 нових статей за один цикл з кожного розділу
        # щоб не флудити канал при першому запуску
        for url in new_links[:2]:
            data = fetch_article_text(url)
            if data:
                new_articles.append({"url": url, "data": data})

    return new_articles


# --- Тест для ручного запуску ---
if __name__ == "__main__":
    print("🧪 Тестую парсер autoconsulting.ua...\n")
    results = get_new_articles(set())
    print(f"\n📊 Всього знайдено статей: {len(results)}")
    for r in results[:3]:
        print(f"\n🔗 URL: {r['url']}")
        print(f"📰 Заголовок: {r['data']['title']}")
        print(f"🖼️  Фото: {r['data']['image']}")
        print(f"📝 Текст (перші 200 символів): {r['data']['text'][:200]}")
