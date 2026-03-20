import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

# ✅ Прибрали: Ринок вантажівок, Ринок автобусів — не релевантно для легкових авто
SECTIONS = [
    {"name": "Ринок автомобілів",         "url": "https://autoconsulting.ua/news.php?catid=16"},
    {"name": "Новини виробників",          "url": "https://autoconsulting.ua/news.php?catid=4"},
    {"name": "Електромобілі",              "url": "https://autoconsulting.ua/news.php?catid=39"},
    {"name": "Статистика автопродажів",    "url": "https://autoconsulting.ua/news.php?catid=41"},
    {"name": "Виробництво автомобілів",    "url": "https://autoconsulting.ua/news.php?catid=17"},
    {"name": "Законодавство",              "url": "https://autoconsulting.ua/news.php?catid=13"},
    {"name": "Автобізнес LIFE",            "url": "https://autoconsulting.ua/news.php?catid=38"},
    {"name": "Дилерська мережа",           "url": "https://autoconsulting.ua/news.php?catid=35"},
    {"name": "Кредити/лізинг/страхування", "url": "https://autoconsulting.ua/news.php?catid=34"},
    {"name": "Авто-електроніка",           "url": "https://autoconsulting.ua/news.php?catid=11"},
    {"name": "Ринок запчастин",            "url": "https://autoconsulting.ua/news.php?catid=8"},
    {"name": "Ринок шин",                  "url": "https://autoconsulting.ua/news.php?catid=30"},
]

BASE_URL = "https://autoconsulting.ua"
KYIV_TZ  = pytz.timezone("Europe/Kiev")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk,ru;q=0.9,en;q=0.8",
}

def get_today_kyiv():
    return datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "windows-1251"
        return r.text
    except Exception as e:
        print(f"❌ [AutoConsulting] Помилка: {url}: {type(e).__name__}: {e}")
        return None

def get_article_links(section_url):
    html = fetch_page(section_url)
    if not html:
        return []
    soup  = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "article.php?sid=" not in href:
            continue
        full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
        if full_url not in links:
            links.append(full_url)
    return links

def parse_article_date(soup):
    text  = soup.get_text(" ")
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}', text)
    return match.group(1) if match else None

def fetch_article_text(article_url, today):
    html = fetch_page(article_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    article_date = parse_article_date(soup)
    if article_date is None:
        print(f"⚠️ [AutoConsulting] Дата не знайдена — пропускаємо: {article_url}")
        return None

    if article_date != today:
        print(f"⏭️ [AutoConsulting] Стара ({article_date} ≠ {today}) — пропускаємо")
        return None

    title = ""
    title_tag = soup.find("title")
    if title_tag:
        raw   = title_tag.get_text(strip=True)
        title = raw.split(":")[0].strip() if ":" in raw else raw

    best_td, best_len = None, 0
    for td in soup.find_all("td"):
        t = td.get_text(separator=" ", strip=True)
        if len(t) > best_len:
            best_len = len(t)
            best_td  = td

    if best_td:
        for tag in best_td.find_all(["script", "style", "a"]):
            tag.decompose()
        text = best_td.get_text(separator="\n", strip=True)
    else:
        text = ""

    if not text or len(text) < 100:
        print(f"⚠️ [AutoConsulting] Текст не знайдено: {article_url}")
        return None

    image_url = None
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png"]):
            if not any(skip in src.lower() for skip in ["adclick", "banner", "logo", "icon", "button"]):
                image_url = src if src.startswith("http") else BASE_URL + "/" + src.lstrip("/")
                break

    # Перевірка стоп-слів — відсіюємо вантажівки, автобуси тощо
    if not is_title_relevant(title):
        return None

    print(f"✅ [AutoConsulting] Свіжа ({article_date}): {title[:60]}...")
    return {"text": text, "title": title, "image": image_url}

# Стоп-слова: якщо є в заголовку — стаття не для нашого каналу
STOP_WORDS = [
    "вантажівк", "тягач", "напівпричіп", "автобус", "тролейбус",
    "мотоцикл", "скутер", "квадроцикл", "трактор", "комбайн",
    "причіп", "фура", "volvo fh", "man tg", "daf xf", "scania",
    "iveco stralis", "mercedes actros",
]

def is_title_relevant(title):
    """Повертає False якщо заголовок містить стоп-слова."""
    title_lower = title.lower()
    for word in STOP_WORDS:
        if word in title_lower:
            print(f"🚫 Стоп-слово '{word}' знайдено: {title[:60]}")
            return False
    return True

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title.lower()).strip()

def save_url_to_file(url, db_file="parsed_urls.txt"):
    with open(db_file, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def get_new_articles(processed_urls, max_total=3):
    today        = get_today_kyiv()
    new_articles = []
    seen_titles  = set()
    seen_urls    = set()

    print(f"\n📅 AutoConsulting: шукаємо статті за {today}")

    for section in SECTIONS:
        if len(new_articles) >= max_total:
            break

        print(f"📡 [{section['name']}]", end=" ")
        links = get_article_links(section["url"])

        # Перевіряємо тільки перші 5 посилань з розділу — решта архів
        for url in links[:5]:
            if len(new_articles) >= max_total:
                break
            if url in processed_urls or url in seen_urls:
                continue

            seen_urls.add(url)
            data = fetch_article_text(url, today)

            if data is None:
                processed_urls.add(url)
                save_url_to_file(url)
                continue

            norm = normalize_title(data["title"])
            if norm in seen_titles:
                print(f"⏭️ Дубль: {data['title'][:50]}")
                processed_urls.add(url)
                save_url_to_file(url)
                continue

            seen_titles.add(norm)
            new_articles.append({"url": url, "data": data})

    if not new_articles:
        print(f"ℹ️ AutoConsulting: свіжих статей за {today} не знайдено.")

    return new_articles

if __name__ == "__main__":
    print("🧪 Тестую autoconsulting.ua...\n")
    results = get_new_articles(set())
    print(f"\n📊 Знайдено сьогоднішніх статей: {len(results)}")
    for r in results:
        print(f"\n🔗 {r['url']}")
        print(f"📰 {r['data']['title']}")
