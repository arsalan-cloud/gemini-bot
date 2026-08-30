import os
import threading
from flask import Flask
import requests
import io
import urllib.parse
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ==========================================
# وب‌سرور جهت فعال نگه داشتن ۲۴ ساعته در Render
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)
# ==========================================

# ==========================================
# تنظیمات کلیدها
TELEGRAM_TOKEN = '8997663787:AAFIZU23Y-W-66Jx0MR2yMosAALvy5kX0NU'
GEMINI_API_KEY = 'AQ.Ab8RN6IPLOJ53K0xCXxL6oxhB6k59ljptajaB-HB5jyujjKoAg'
# ==========================================

system_prompt = (
    "شما یک دستیار هوش مصنوعی بسیار باهوش و خوش‌برخورد به نام Alex AI هستید. "
    "به تمام پیام‌های کاربر به‌صورت کاملاً روان، دقیق و طبیعی به زبان فارسی پاسخ دهید."
)

def ask_gemini(user_text):
    clean_key = GEMINI_API_KEY.strip().encode('ascii', 'ignore').decode('ascii')
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # استفاده از ساختار Bearer برای توکن‌های AQ
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {clean_key}'
    }
    payload = {
        "contents": [{"parts": [{"text": user_text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }

    try:
        res = requests.post(gemini_url, headers=headers, json=payload, timeout=30)
        res_json = res.json()
        if "candidates" in res_json and len(res_json["candidates"]) > 0:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        elif "error" in res_json:
            return f"خطای جمینای: {res_json['error'].get('message', 'خطای ناشناخته')}"
        else:
            return "پاسخی دریافت نشد."
    except Exception as e:
        return f"خطا در ارتباط با سرور: {str(e)}"

def generate_ai_image_prompt(user_text):
    clean_key = GEMINI_API_KEY.strip().encode('ascii', 'ignore').decode('ascii')
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    prompt_instruction = (
        "Translate and enhance the following user request into a detailed English image generation prompt. "
        "Output ONLY the final English prompt string, without any additional explanations, quotes, or conversational text."
    )

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {clean_key}'
    }
    payload = {
        "contents": [{"parts": [{"text": user_text}]}],
        "systemInstruction": {"parts": [{"text": prompt_instruction}]}
    }

    try:
        res = requests.post(gemini_url, headers=headers, json=payload, timeout=15)
        res_json = res.json()
        if "candidates" in res_json and len(res_json["candidates"]) > 0:
            return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return user_text

def create_ai_image(prompt_en):
    encoded_prompt = urllib.parse.quote(prompt_en)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"

    try:
        res = requests.get(image_url, timeout=40)
        if res.status_code == 200 and len(res.content) > 5000:
            return io.BytesIO(res.content)
    except Exception as e:
        print(f"Error generating image: {e}")
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('سلام! من دستیار هوشمند Alex AI هستم. می‌توانید با من گفتگو کنید یا درخواست ساخت عکس اختصاصی با هوش مصنوعی بدهید.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    text_lower = user_text.lower()

    image_keywords = ['عکس', 'تصویر', 'بساظ', 'بفرست', 'خلق کن', 'بکش', 'طراحی کن']
    is_question = any(q in text_lower for q in ['میتونی', 'می‌توانی', 'آیا', 'ایا', 'چرا', 'چطور', 'چگونه', 'ادیت', 'ویرایش'])
    wants_image = any(kw in text_lower for kw in image_keywords) and not is_question

    if wants_image:
        await context.bot.send_chat_action(chat_id=chat_id, action='upload_photo')
        await update.message.reply_text('🎨 در حال ساخت تصویر اختصاصی شما با هوش مصنوعی... لطفاً چند لحظه صبر کنید.')

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
