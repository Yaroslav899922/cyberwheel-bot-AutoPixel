"""
test_weekly_now.py — ТІЛЬКИ ДЛЯ ТЕСТУ, не чіпає жоден робочий файл.

Що робить:
1. Заповнює weekly_headlines в Redis реальними статтями з сьогоднішніх логів
2. Викликає send_weekly_digest() — відправляє в Telegram прямо зараз
3. Після тесту — очищає weekly_headlines (щоб не заважало реальній роботі)

Запуск: python test_weekly_now.py
"""

import weekly_digest

# ── РЕАЛЬНІ СТАТТІ З ЛОГІВ СЬОГОДНІ 29.03.2026 ───────────────────────────────
# Взяті напряму з Render логів — це те що бот вже опублікував сьогодні
TEST_HEADLINES = [
    {
        "title": "This Lamborghini Repair Started At $1,200 Until The Mechanic Found The $40 Ford Part Inside It",
        "url":   "https://www.carscoops.com/2026/03/aventador-repair-ford-parts/"
    },
    {
        "title": "Reverse in, drive out: It's time to get parking right, for good",
        "url":   "https://www.autocar.co.uk/opinion/features/reverse-drive-out-its-time-get-parking-right-good"
    },
    {
        "title": "How Singer built an empire without a business plan",
        "url":   "https://www.autocar.co.uk/car-news/podcasts-my-week-in-cars/how-singer-built-empire-without-business-plan"
    },
    {
        "title": "Lotus Eletre X plug-in hybrid SUV launched in China for 73,500 USD",
        "url":   "https://carnewschina.com/2026/03/29/lotus-eletre-x-plug-in-hybrid-suv-launched-in-china-for-73500-usd/"
    },
    # Додаємо з Redis parsed_urls (motor1) — для повноти вибірки Gemini
    {
        "title": "BMW M5 Facelift Spy Video",
        "url":   "https://www.motor1.com/news/791307/bmw-m5-facelift-spy-video/"
    },
    {
        "title": "Acura Integra Tribute Race Car 40th Anniversary",
        "url":   "https://www.motor1.com/news/791348/acura-integra-tribute-race-car-40th-annivesary/"
    },
    {
        "title": "Koenigsegg Gemera Finally Enters Production",
        "url":   "https://www.motor1.com/news/791396/koenigsegg-gemera-finally-enters-productiond/"
    },
    {
        "title": "2026 Hyundai Palisade Seat Belt Recall",
        "url":   "https://www.motor1.com/news/791359/2026-hyundai-palisade-seat-belt-recall/"
    },
    {
        "title": "Aston Martin DBX Review",
        "url":   "https://www.motor1.com/reviews/790439/aston-martin-dbx-s-review/"
    },
    {
        "title": "Porsche Cayenne Electric First Drive",
        "url":   "https://www.motor1.com/reviews/791248/porsche-cayenne-electric-first-drive/"
    },
]

def run_test():
    print("=" * 55)
    print("🧪 ТЕСТ ТИЖНЕВОГО ДАЙДЖЕСТУ")
    print("=" * 55)

    # Крок 1: Очищаємо старий ключ (якщо є залишки)
    print("\n🗑️  Крок 1: Очищаю weekly_headlines в Redis...")
    weekly_digest._redis(["DEL", weekly_digest.WEEKLY_KEY])
    print("   ✅ Очищено")

    # Крок 2: Заповнюємо тестовими даними
    print(f"\n📝 Крок 2: Додаю {len(TEST_HEADLINES)} тестових заголовків...")
    for item in TEST_HEADLINES:
        weekly_digest.add_headline_to_weekly(item["title"], item["url"])
    print(f"   ✅ Додано {len(TEST_HEADLINES)} записів")

    # Крок 3: Перевіряємо що записалось
    print("\n🔍 Крок 3: Перевіряю що в Redis...")
    saved = weekly_digest.get_weekly_headlines()
    print(f"   Знайдено в Redis: {len(saved)} заголовків")
    for i, h in enumerate(saved, 1):
        print(f"   {i}. {h['title'][:60]}")

    # Крок 4: Показуємо діапазон дат
    print(f"\n📅 Крок 4: Діапазон дат → '{weekly_digest.get_week_range_label()}'")

    # Крок 5: Відправляємо дайджест
    print("\n🚀 Крок 5: Відправляю тижневий дайджест у Telegram...")
    print("-" * 55)

    # Викликаємо напряму build+send щоб не спрацював маркер файлу
    # (маркер потрібен тільки для реального розкладу)
    message = weekly_digest.build_weekly_digest_message()

    if message:
        import telegram_bot
        success = telegram_bot.send_telegram_message(text=message)
        if success:
            print("\n✅ ТЕСТ УСПІШНИЙ! Перевір Telegram-канал.")
        else:
            print("\n❌ Помилка відправки в Telegram.")
    else:
        print("\n❌ Повідомлення не сформовано — перевір лог вище.")

    print("=" * 55)
    print("ℹ️  Після тесту weekly_headlines в Redis очищено автоматично.")
    print("   Реальний дайджест почне збиратись з першої публікації.")
    print("=" * 55)

if __name__ == "__main__":
    run_test()
