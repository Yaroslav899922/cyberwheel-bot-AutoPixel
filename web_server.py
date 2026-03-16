import os
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 AutoPixel AI News Bot is Running 24/7!"

def run():
    # Render та інші сервіси автоматично присвоюють порт через змінну середовища PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Запускає веб-сервер у фоновому потоці, щоб хмарні сервіси не вимикали бота"""
    t = Thread(target=run)
    t.daemon = True
    t.start()
