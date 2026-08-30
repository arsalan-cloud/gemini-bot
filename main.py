import os
import threading
from flask import Flask

# ۱. تعریف وب‌سرور Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

# ۲. تابع اجرای ربات تلگرام
def run_telegram_bot():
    # --- تمام کدهای اصلی ربات تلگرام شما در این قسمت قرار می‌گیرد ---
    # مثال: bot.infinity_polling() یا app.run_polling()
    pass

# ۳. شروع اجرای ربات تلگرام در پس‌زمینه
threading.Thread(target=run_telegram_bot, daemon=True).start()

# ۴. اجرای Flask در نخ اصلی (این بخش مانع از بسته شدن پایتون می‌شود)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
