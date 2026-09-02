import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# =========================================================
# 1. Health Check Web Server (Fixes UptimeRobot 501 HEAD error)
# =========================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot is active!")

    # Route HEAD requests to do_GET so UptimeRobot reports 200 OK
    do_HEAD = do_GET

    def log_message(self, format, *args):
        # Suppress standard HTTP request log spam on Render
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ("", port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"Health check web server running on port {port}...")
    httpd.serve_forever()

# =========================================================
# 2. Telegram Bot Configuration
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("CRITICAL ERROR: 'BOT_TOKEN' environment variable is missing!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_start = types.KeyboardButton("🇦🇫 Welcome")
    btn_info = types.KeyboardButton("ℹ️ My Info")
    btn_ping = types.KeyboardButton("⚡ Ping Status")
    btn_help = types.KeyboardButton("❓ Help")
    markup.add(btn_start, btn_info, btn_ping, btn_help)
    return markup

# =========================================================
# 3. Command Handlers
# =========================================================

# /start command with Afghanistan Flag and Greetings
@bot.message_handler(commands=['start'])
@bot.message_handler(func=lambda message: message.text == "🇦🇫 Welcome")
def send_welcome(message):
    first_name = message.from_user.first_name or "Friend"
    
    welcome_text = (
        f"🇦🇫 **Salam & Welcome, {first_name}!** 🇦🇫\n"
        f" خوش آمدید / پخیر راغلاست\n\n"
        f"Your Telegram bot is fully active, operational, and running 24/7 on Render!\n\n"
        f"Use the buttons below to check your profile info or test bot performance."
    )
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )

# /info command to display user details
@bot.message_handler(commands=['info'])
@bot.message_handler(func=lambda message: message.text == "ℹ️ My Info")
def send_info(message):
    user = message.from_user
    first_name = user.first_name or "N/A"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "None"
    user_id = user.id
    language = user.language_code or "en"
    is_premium = "Yes ⭐" if getattr(user, 'is_premium', False) else "No"

    info_text = (
        f"👤 **User Account Info**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"▪️ **Full Name:** {full_name}\n"
        f"▪️ **Username:** {username}\n"
        f"▪️ **User ID:** `{user_id}`\n"
        f"▪️ **Language:** `{language}`\n"
        f"▪️ **Telegram Premium:** {is_premium}\n\n"
        f"🤖 **Bot Status:** Active 🟢"
    )
    bot.send_message(
        message.chat.id, 
        info_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )

# /ping command to measure latency
@bot.message_handler(commands=['ping'])
@bot.message_handler(func=lambda message: message.text == "⚡ Ping Status")
def send_ping(message):
    start_time = time.time()
    sent_msg = bot.send_message(message.chat.id, "🏓 Measuring ping...")
    end_time = time.time()
    latency = round((end_time - start_time) * 1000, 2)
    
    bot.edit_message_text(
        f"🏓 **Pong!**\n"
        f"⚡ **Response Time:** `{latency} ms`\n"
        f"🟢 **Server Health:** 100% Active", 
        message.chat.id, 
        sent_msg.message_id, 
        parse_mode="Markdown"
    )

# /help command
@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text == "❓ Help")
def send_help(message):
    help_text = (
        f"🛠 **Available Commands:**\n\n"
        f"• `/start` - Display welcome message & greetings 🇦🇫\n"
        f"• `/info` - View your Telegram profile details & ID\n"
        f"• `/ping` - Check server latency and status\n"
        f"• `/help` - Display this menu"
    )
    bot.send_message(
        message.chat.id, 
        help_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )

# Echo fallback for any other text messages
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message, 
        "Message received! Select an option from the menu below:", 
        reply_markup=get_main_keyboard()
    )

# =========================================================
# 4. Entry Point
# =========================================================
if __name__ == "__main__":
    # Start web server thread for Render & UptimeRobot
    server_thread = threading.Thread(target=run_health_check_server, daemon=True)
    server_thread.start()

    print("Telegram bot polling started...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
