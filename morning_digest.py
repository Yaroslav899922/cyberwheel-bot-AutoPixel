import requests
import os
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
# Ключі беруться з Render → Environment Variables
# WEATHER_API_KEY — з openweathermap.org
# CoinGecko більше не потрібен — використовуємо Binance Public API (безкоштовно, без ключа)
# ─────────────────────────────────────────────
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

CITY    = "Kremenchuk"
CITY_UA = "Кременчук"

def get_weather():
    if not WEATHER_API_KEY:
        return "🌤️ <b>Погода:</b> ключ WEATHER_API_KEY не налаштовано на Render"
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={CITY}&appid={WEATHER_API_KEY}&units=metric&lang=uk"
        )
        r = requests.get(url, timeout=10)
        d = r.json()

        temp     = round(d["main"]["temp"])
        feels    = round(d["main"]["feels_like"])
        humidity = d["main"]["humidity"]
        wind     = round(d["wind"]["speed"])
        desc     = d["weather"][0]["description"].capitalize()

        desc_lower = desc.lower()
        if any(w in desc_lower for w in ["ясно", "сонячно"]):
            icon = "☀️"
        elif any(w in desc_lower for w in ["хмарно", "похмуро"]):
            icon = "☁️"
        elif any(w in desc_lower for w in ["дощ", "злива", "морось"]):
            icon = "🌧️"
        elif "сніг" in desc_lower:
            icon = "❄️"
        elif "туман" in desc_lower:
            icon = "🌫️"
        elif "гроза" in desc_lower:
            icon = "⛈️"
        else:
            icon = "🌤️"

        return (
            f"{icon} <b>Погода · {CITY_UA}</b>\n"
            f"Температура: <b>{temp}°C</b>, відчувається як {feels}°C\n"
            f"{desc} · Вітер: {wind} м/с · Вологість: {humidity}%"
        )
    except Exception as e:
        print(f"⚠️ [Дайджест] Помилка погоди: {type(e).__name__}: {e}")
        return "🌤️ <b>Погода:</b> тимчасово недоступна"


def get_currency():
    """НБУ API — безкоштовно, без ключа."""
    try:
        url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
        r = requests.get(url, timeout=10)
        data = r.json()

        rates = {}
        for item in data:
            if item["cc"] in ("USD", "EUR"):
                rates[item["cc"]] = item["rate"]

        usd = f"{rates['USD']:.2f}" if "USD" in rates else "н/д"
        eur = f"{rates['EUR']:.2f}" if "EUR" in rates else "н/д"

        return (
            f"💵 <b>Курси валют · НБУ</b>\n"
            f"USD: <b>{usd} грн</b>\n"
            f"EUR: <b>{eur} грн</b>"
        )
    except Exception as e:
        print(f"⚠️ [Дайджест] Помилка курсів: {type(e).__name__}: {e}")
        return "💵 <b>Курси валют:</b> тимчасово недоступні"


def get_crypto():
    """
    Binance Public API — повністю безкоштовно, без реєстрації, без ключа.
    Один запит повертає ціну будь-якої пари до USDT.
    Також окремо беремо зміну за 24 години через ticker/24hr.
    """
    coins = {
        "BTCUSDT": "BTC",
        "ETHUSDT": "ETH",
        "BNBUSDT": "BNB",
    }
    lines = ["₿ <b>Крипта · Binance</b>"]

    try:
        # Один запит — всі три пари одразу
        symbols = '["' + '","'.join(coins.keys()) + '"]'
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={symbols}"
        r = requests.get(url, timeout=10)
        data = r.json()

        for item in data:
            symbol = item["symbol"]
            name   = coins.get(symbol, symbol)
            price  = float(item["lastPrice"])
            change = float(item["priceChangePercent"])

            arrow = "📈" if change >= 0 else "📉"
            sign  = "+" if change >= 0 else ""
            price_str = f"{price:,.0f}" if price > 1000 else f"{price:,.2f}"

            lines.append(f"{arrow} {name}: <b>${price_str}</b> ({sign}{change:.1f}%)")

        return "\n".join(lines)

    except Exception as e:
        print(f"⚠️ [Дайджест] Помилка крипти: {type(e).__name__}: {e}")
        return "₿ <b>Крипта:</b> тимчасово недоступна"


def build_morning_digest():
    """Збирає всі три блоки в одне повідомлення."""
    kyiv_tz = pytz.timezone("Europe/Kiev")
    now = datetime.now(kyiv_tz)

    days_ua = {
        0: "Понеділок", 1: "Вівторок",  2: "Середа",
        3: "Четвер",    4: "П'ятниця",  5: "Субота", 6: "Неділя"
    }
    day_name = days_ua[now.weekday()]
    date_str = now.strftime("%d.%m.%Y")

    weather  = get_weather()
    currency = get_currency()
    crypto   = get_crypto()

    message = (
        f"🌅 <b>РАНКОВИЙ ДАЙДЖЕСТ · {day_name}, {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{weather}\n\n"
        f"{currency}\n\n"
        f"{crypto}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🚗 Гарного дня та безпечної дороги!\n"
        f"<i>Skoda Kremen News</i>"
    )
    return message


if __name__ == "__main__":
    print("🧪 Тестую ранковий дайджест...\n")
    msg = build_morning_digest()
    print(msg)
