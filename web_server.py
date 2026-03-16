from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 AutoPixel AI News Bot is Running 24/7!"

def run():
    # Render використовує порт 10000 за замовчуванням
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    """Запускає сервер у фоновому потоці"""
    t = Thread(target=run)
    t.start()