
import os
import threading
from flask import Flask

# سرور ساختگی برای زنده نگه داشتن سرویس در Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# اجرای وب سرور در پس‌زمینه
threading.Thread(target=run_web, daemon=True).start()
