from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "🤖 AutoPixel AI News Bot is Running 24/7!"

def run():
    # Render сам підставить правильний порт, або візьме 10000 як запасний
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Запускає сервер у фоновому потоці (демоном)"""
    t = Thread(target=run)
    t.daemon = True # Тепер він точно не заблокує парсер!
    t.start()
