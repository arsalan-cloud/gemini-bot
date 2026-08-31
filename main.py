import os
import threading
import urllib.parse
import requests
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from google import genai

# ==========================================
# 🔑 تنظیم کلیدها
# ==========================================
# کلید شروع شونده با AIzaSy را اینج
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6KXG9t1MuvZKzJRG1HR6GTsHmF7a8n5O0_5ZDq_Oz5rxw")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8997663787:AAFIZU23Y-W-66Jx0MR2yMosAALvy5kX0NU")
# ==========================================

# ساخت کلاینت هوش مصنوعی
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# وب‌سرور Flask برای Render
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running live!"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# پاسخ‌دهی متنی استاندارد با API Key
def ask_gemini(user_text: str) -> str:
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text
        )
        return response.text
    except Exception as e:
        return f"خطای جمینای: {str(e)}"

# ترجمه متن فارسی به پرامپت انگلیسی برای تصویر
def generate_ai_image_prompt(user_text: str) -> str:
    prompt_instruction = (
        "Translate and refine the following Persian user input into a concise, "
        "detailed English prompt suitable for an AI image generator. "
        f"Output ONLY the English prompt without any extra explanation: {user_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_instruction
        )
        return response.text.strip()
    except Exception:
        return user_text

# تولید تصویر رایگان
def create_ai_image(prompt: str):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception:
        return None

# دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من ربات الکس هستم.\nمی‌توانید از من سوال بپرسید یا برای دریافت عکس، متنی مثل «عکس یک گربه» ارسال کنید."
    )

# مدیریت پیام‌های تلگرام
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    text_lower = user_text.lower()

    image_keywords = ['عکس', 'تصویر', 'بساط', 'بفرست', 'خلق کن', 'بکش', 'طراحی کن']
    is_question = any(q in text_lower for q in ['میتونی', 'می‌توانی', 'آیا', 'ایا', 'چرا', 'چطور', 'چگونه', 'ادیت', 'ویرایش'])
    wants_image = any(kw in text_lower for kw in image_keywords) and not is_question

    if wants_image:
        await context.bot.send_chat_action(chat_id=chat_id, action='upload_photo')
        await update.message.reply_text('🎨 در حال ساخت تصویر اختصاصی شما... لطفاً چند لحظه صبر کنید.')

        en_prompt = generate_ai_image_prompt(user_text)
        image_bytes = create_ai_image(en_prompt)

        if image_bytes:
            await update.message.reply_photo(
                photo=image_bytes,
                caption=f"✨ تصویر تولید شده با هوش مصنوعی\n📝 پرامپت انگلیسی: {en_prompt}"
            )
        else:
            await update.message.reply_text('متأسفانه در ساخت تصویر خطایی رخ داد. لطفاً دوباره تلاش کنید.')
        return

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    ai_reply = ask_gemini(user_text)
    await update.message.reply_text(ai_reply)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()
