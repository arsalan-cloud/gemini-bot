import os
import asyncio
import threading
import logging
import urllib.parse
import requests

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not configured in Render Environment Variables."
    )

if not TELEGRAM_TOKEN:
    raise RuntimeError(
        "TELEGRAM_TOKEN is not configured in Render Environment Variables."
    )


# =========================================================
# GEMINI CLIENT
# =========================================================

try:
    genai.configure(api_key=GEMINI_API_KEY.strip())
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("Gemini client initialized successfully.")
except Exception as e:
    logger.exception("Failed to initialize Gemini client.")
    raise


# =========================================================
# FLASK SERVER FOR RENDER
# =========================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Alex Ai Bot is running."


@flask_app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "10000"))
    flask_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


# =========================================================
# GEMINI TEXT GENERATION
# =========================================================

def _ask_gemini_sync(user_text: str) -> str:
    try:
        response = gemini_model.generate_content(user_text)

        if response and getattr(response, "text", None):
            return response.text.strip()

        return "متأسفانه پاسخی از Gemini دریافت نشد."

    except Exception as e:
        error_text = str(e)
        logger.error("Gemini API error: %s", error_text)

        if "401" in error_text or "UNAUTHENTICATED" in error_text or "API_KEY_INVALID" in error_text:
            return (
                "❌ خطا در احراز هویت Gemini.\n\n"
                "کلید GEMINI_API_KEY در تنظیمات Render را بررسی کنید "
                "و مطمئن شوید کلید معتبر از Google AI Studio وارد شده است."
            )

        if "429" in error_text:
            return "⏳ تعداد درخواست‌های Gemini زیاد شده است. لطفاً چند لحظه بعد دوباره امتحان کنید."

        return "❌ در ارتباط با Gemini خطایی رخ داد. لطفاً چند لحظه بعد دوباره امتحان کنید."


async def ask_gemini(user_text: str) -> str:
    return await asyncio.to_thread(_ask_gemini_sync, user_text)


# =========================================================
# TRANSLATE IMAGE PROMPT
# =========================================================

def _generate_ai_image_prompt_sync(user_text: str) -> str:
    instruction = f"""
Translate and improve the following Persian request into a
high-quality English prompt for an AI image generator.

Requirements:
- Output ONLY the English image prompt.
- Do not explain anything.
- Make the prompt detailed and visually descriptive.
- Preserve the user's original intention.

Persian request:
{user_text}
"""
    try:
        response = gemini_model.generate_content(instruction)

        if response and getattr(response, "text", None):
            return response.text.strip()

        return user_text

    except Exception as e:
        logger.error("Image prompt generation error: %s", str(e))
        return user_text


async def generate_ai_image_prompt(user_text: str) -> str:
    return await asyncio.to_thread(_generate_ai_image_prompt_sync, user_text)


# =========================================================
# IMAGE GENERATION
# =========================================================

def _create_ai_image_sync(prompt: str):
    try:
        encoded_prompt = urllib.parse.quote(prompt, safe="")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

        response = requests.get(
            url,
            timeout=60,
            headers={"User-Agent": "AlexAiTelegramBot/1.0"},
        )

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("image/"):
                return response.content

        logger.error("Image API returned status %s", response.status_code)
        return None

    except Exception as e:
        logger.error("Image generation error: %s", str(e))
        return None


async def create_ai_image(prompt: str):
    return await asyncio.to_thread(_create_ai_image_sync, prompt)


# =========================================================
# /START COMMAND
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    await update.message.reply_text(
        "سلام 👋\n\n"
        "من الکس، دستیار هوش مصنوعی شما هستم 🤖\n\n"
        "می‌توانید سؤال بپرسید یا برای ساخت تصویر "
        "مثلاً بنویسید:\n\n"
        "🎨 عکس یک گربه در فضا بساز"
    )


# =========================================================
# TELEGRAM MESSAGE HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    chat_id = update.effective_chat.id
    text_lower = user_text.lower()

    image_keywords = [
        "عکس", "تصویر", "بساز", "خلق کن", "بکش", 
        "طراحی کن", "تصویرسازی", "عکس بساز", "تصویر بساز"
    ]

    question_keywords = [
        "میتونی", "می‌تونی", "می‌توانی", "میتوانی", 
        "آیا", "ایا", "چرا", "چطور", "چگونه", "ادیت", "ویرایش"
    ]

    wants_image = (
        any(word in text_lower for word in image_keywords)
        and not any(word in text_lower for word in question_keywords)
    )

    if wants_image:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
            await update.message.reply_text(
                "🎨 در حال آماده‌سازی تصویر شما...\nلطفاً کمی صبر کنید."
            )

            en_prompt = await generate_ai_image_prompt(user_text)
            image_bytes = await create_ai_image(en_prompt)

            if image_bytes:
                await update.message.reply_photo(
                    photo=image_bytes,
                    caption=f"✨ تصویر شما آماده شد!\n\n📝 Prompt:\n{en_prompt}",
                )
            else:
                await update.message.reply_text(
                    "❌ متأسفانه ساخت تصویر انجام نشد.\nلطفاً دوباره امتحان کنید."
                )

        except Exception as e:
            logger.exception("Image request failed: %s", str(e))
            await update.message.reply_text("❌ هنگام ساخت تصویر خطایی رخ داد.")

        return

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        ai_reply = await ask_gemini(user_text)
        await update.message.reply_text(ai_reply)

    except Exception as e:
        logger.exception("Message handling error: %s", str(e))
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً دوباره امتحان کنید.")


# =========================================================
# MAIN
# =========================================================

def main():
    logger.info("Starting Alex Ai Telegram Bot...")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot is starting polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    main()
