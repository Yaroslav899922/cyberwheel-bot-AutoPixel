from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "🤖 AutoPulse News Bot is Running 24/7!"

# ── ТИМЧАСОВИЙ МАРШРУТ ДЛЯ ТЕСТУ ДАЙДЖЕСТУ ──────────────────────────────────
# Після успішного тесту — видали цей блок і залий знову на GitHub
@app.route('/test-weekly')
def test_weekly():
    try:
        import test_weekly_now
        test_weekly_now.run_test()
        return "✅ Тест запущено! Перевір Telegram-канал."
    except Exception as e:
        return f"❌ Помилка: {e}"
# ─────────────────────────────────────────────────────────────────────────────

# ── СТАТИСТИКА ПУБЛІКАЦІЙ ────────────────────────────────────────────────────
@app.route('/stats')
def stats():
    from auto_parser import _redis
    from datetime import datetime, timedelta
    import pytz

    KYIV = pytz.timezone("Europe/Kiev")
    now = datetime.now(pytz.utc).astimezone(KYIV)

    rows = []
    total = 0
    for i in range(7):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        r = _redis(["GET", f"daily_stats:{day}"])
        count = int(r["result"]) if r and r.get("result") else 0
        total += count
        rows.append(
            f"<tr><td>{day}</td><td style='text-align:center'>{count}</td></tr>"
        )

    html = f"""
    <html><head><meta charset='utf-8'>
    <title>AutoPulse Stats</title>
    <style>
      body {{ font-family: sans-serif; background:#0f1117; color:#e2e8f0; padding:30px; }}
      h1 {{ color:#38bdf8; }}
      table {{ border-collapse:collapse; margin-top:20px; }}
      td, th {{ border:1px solid #334155; padding:10px 24px; }}
      th {{ background:#1e293b; color:#38bdf8; }}
      .total {{ margin-top:20px; font-size:18px; color:#22c55e; }}
    </style></head><body>
    <h1>📊 AutoPulse — Статистика публікацій</h1>
    <table>
      <tr><th>Дата</th><th>Публікацій</th></tr>
      {''.join(rows)}
    </table>
    <p class='total'>Всього за 7 днів: {total}</p>
    </body></html>
    """
    return html
# ─────────────────────────────────────────────────────────────────────────────

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Запускає сервер у фоновому потоці (демоном)"""
    t = Thread(target=run)
    t.daemon = True
    t.start()
