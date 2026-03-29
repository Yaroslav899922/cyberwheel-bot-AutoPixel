from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "🤖 AutoPixel AI News Bot is Running 24/7!"

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

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Запускає сервер у фоновому потоці (демоном)"""
    t = Thread(target=run)
    t.daemon = True
    t.start()
