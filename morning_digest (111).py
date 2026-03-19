import requests
import os
from datetime import datetime
import pytz

WEATHER_API_KEY    = os.getenv("WEATHER_API_KEY", "")
CMC_API_KEY = os.getenv("CMC_API_KEY", "")

CITY    = "Kremenchuk,UA"
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
    """CoinMarketCap API — безкоштовний план, 10k запитів/місяць."""
    if not CMC_API_KEY:
        return "₿ <b>Крипта:</b> ключ CMC_API_KEY не налаштовано на Render"
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
        params  = {"symbol": "BTC,ETH,BNB", "convert": "USD"}

        r = requests.get(url, headers=headers, params=params, timeout=10)
        d = r.json()
        coins_data = d.get("data", {})

        lines = ["₿ <b>Крипта · CoinMarketCap</b>"]

        for symbol in ["BTC", "ETH", "BNB"]:
            info   = coins_data.get(symbol, {})
            quote  = info.get("quote", {}).get("USD", {})
            price  = quote.get("price", 0)
            change = quote.get("percent_change_24h", 0)

            if not price:
                lines.append(f"• {symbol}: н/д")
                continue

            arrow     = "📈" if change >= 0 else "📉"
            sign      = "+" if change >= 0 else ""
            price_str = f"{price:,.0f}" if price > 1000 else f"{price:,.2f}"
            lines.append(f"{arrow} {symbol}: <b>${price_str}</b> ({sign}{change:.1f}%)")

        return "\n".join(lines)

    except Exception as e:
        print(f"⚠️ [Дайджест] Помилка крипти: {type(e).__name__}: {e}")
        return "₿ <b>Крипта:</b> тимчасово недоступна"


def build_morning_digest():
    kyiv_tz = pytz.timezone("Europe/Kiev")
    now = datetime.now(kyiv_tz)

    days_ua = {
        0: "понеділок", 1: "вівторок",  2: "середу",
        3: "четвер",    4: "п'ятницю",  5: "суботу", 6: "неділю"
    }
    day_name = days_ua[now.weekday()]
    date_str = now.strftime("%d.%m.%Y")

    weather  = get_weather()
    currency = get_currency()
    crypto   = get_crypto()

    message = (
        f"🌅 <b>Добрий ранок!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Агент Софія вітає вас у {day_name}, {date_str}.\n"
        f"Ось все що потрібно знати перед початком дня:\n\n"
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
    print(build_morning_digest())
