import requests
import re
from bs4 import BeautifulSoup

SECTIONS = [
    {"name": "Ринок автомобілів",        "url": "https://autoconsulting.ua/news.php?catid=16"},
    {"name": "Новини виробників",         "url": "https://autoconsulting.ua/news.php?catid=4"},
    {"name": "Електромобілі",             "url": "https://autoconsulting.ua/news.php?catid=39"},
    {"name": "Статистика автопродажів",   "url": "https://autoconsulting.ua/news.php?catid=41"},
    {"name": "Ринок автобусів",           "url": "https://autoconsulting.ua/news.php?catid=5"},
    {"name": "Ринок вантажівок",          "url": "https://autoconsulting.ua/news.php?catid=9"},
    {"name": "Виробництво автомобілів",   "url": "https://autoconsulting.ua/news.php?catid=17"},
    {"name": "Законодавство",             "url": "https://autoconsulting.ua/news.php?catid=13"},
    {"name": "Автобізнес LIFE",           "url": "https://autoconsulting.ua/news.php?catid=38"},
    {"name": "Дилерська мережа",          "url": "https://autoconsulting.ua/news.php?catid=35"},
    {"name": "Кредити/лізинг/страхування","url": "https://autoconsulting.ua/news.php?catid=34"},
    {"name": "Авто-електроніка",          "url": "https://autoconsulting.ua/news.php?catid=11"},
    {"name": "Ринок запчастин",           "url": "https://autoconsulting.ua/news.php?catid=8"},
    {"name": "Ринок шин",                 "url": "https://autoconsulting.ua/news.php?catid=30"},
]

BASE_URL = "https://autoconsulting.ua"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk,ru;q=0.9,en;q=0.8",
}

# Статті з sid нижче цього порогу — архівні, ігноруємо
MIN_SID = 60500

def fetch_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = "windows-1251"
        return response.text
    except Exception as e:
        print(f"❌ [AutoConsulting] Помилка завантаження {url}: {type(e).__name__}: {e}")
        return None

def get_article_links(section_url):
    html = fetch_page(section_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "article.php?sid=" in href:
            sid_match = re.search(r'sid=(\d+)', href)
            if not sid_match:
                continue
            sid = int(sid_match.group(1))
            if sid < MIN_SID:
                continue
            full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            if full_url not in links:
                links.append(full_url)

    return links

def fetch_article_text(article_url):
    html = fetch_page(article_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_tag = soup.find("title")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        title = raw_title.split(":")[0].strip() if ":" in raw_title else raw_title

    text = ""
    best_td = None
    best_len = 0
    for td in soup.find_all("td"):
        td_text = td.get_text(separator=" ", strip=True)
        if len(td_text) > best_len:
            best_len = len(td_text)
            best_td = td

    if best_td:
        for tag in best_td.find_all(["script", "style", "a"]):
            tag.decompose()
        text = best_td.get_text(separator="\n", strip=True)

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

    print(f"✅ [AutoConsulting] Завантажено: {title[:60]}...")
    return {"text": text, "title": title, "image": image_url}

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title.lower()).strip()

def save_url_to_file(url, db_file="parsed_urls.txt"):
    with open(db_file, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def get_new_articles(processed_urls):
    new_articles = []
    seen_titles = set()

    for section in SECTIONS:
        print(f"\n📡 [AutoConsulting] Перевіряю розділ: {section['name']}")
        links = get_article_links(section["url"])
        print(f"   Знайдено свіжих посилань (sid>{MIN_SID}): {len(links)}")

        new_links = [l for l in links if l not in processed_urls]
        print(f"   Нових (не опублікованих): {len(new_links)}")

        for url in new_links[:1]:
            data = fetch_article_text(url)
            if not data:
                continue

            norm = normalize_title(data['title'])
            if norm in seen_titles:
                print(f"⏭️ Пропускаємо дубль: {data['title'][:60]}")
                processed_urls.add(url)
                save_url_to_file(url)
                continue

            seen_titles.add(norm)
            new_articles.append({"url": url, "data": data})

    return new_articles

if __name__ == "__main__":
    print("🧪 Тестую парсер autoconsulting.ua...\n")
    results = get_new_articles(set())
    print(f"\n📊 Знайдено нових статей: {len(results)}")
    for r in results[:3]:
        print(f"\n🔗 {r['url']}")
        print(f"📰 {r['data']['title']}")
        print(f"📝 {r['data']['text'][:150]}")
