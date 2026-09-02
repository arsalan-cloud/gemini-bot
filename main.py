import os
import sys
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot
from telebot import types

# =========================================================
# 1. HEALTH CHECK SERVER (Required for Render & UptimeRobot)
# =========================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is healthy and running 24/7.")

    # Fixes UptimeRobot 501 HEAD error
    do_HEAD = do_GET

    def log_message(self, format, *args):
        # Suppress standard HTTP request log spam on Render
        return

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check web server running on port {port}...")
    server.serve_forever()

# =========================================================
# 2. BOT CONFIG & DATABASE
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("CRITICAL ERROR: 'BOT_TOKEN' environment variable is missing!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE = "users.json"
BASE_URL = "https://ftda-gestion.newmips.cloud/"
pending_registration = set()

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

def translate_status(raw_text):
    text_lower = raw_text.lower()
    if "no mail" in text_lower or "courrier" in text_lower:
        return f"{raw_text}\n\n🇮🇷 **ترجمه فارسی:** شما هیچ نامه‌ای ندارید."
    return f"{raw_text}\n\n🇮🇷 **ترجمه فارسی:** وضعیت دریافت شد."

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_welcome = types.KeyboardButton("🇦🇫 Welcome")
    btn_check = types.KeyboardButton("🔍 Check Status")
    btn_update = types.KeyboardButton("✏️ Update Card")
    btn_info = types.KeyboardButton("ℹ️ My Info")
    btn_ping = types.KeyboardButton("⚡ Ping Status")
    btn_help = types.KeyboardButton("❓ Help")
    markup.add(btn_welcome, btn_check, btn_update, btn_info, btn_ping, btn_help)
    return markup

# =========================================================
# 3. SELENIUM SCRAPER
# =========================================================
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=fr-FR,fr,en-US,en")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    for chrome_path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/data/data/com.termux/files/usr/bin/chromium-browser"]:
        if os.path.exists(chrome_path):
            chrome_options.binary_location = chrome_path
            break

    driver_path = None
    for dp in ["/usr/bin/chromedriver", "/data/data/com.termux/files/usr/bin/chromedriver"]:
        if os.path.exists(dp):
            driver_path = dp
            break

    service = Service(driver_path) if driver_path else Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
        "acceptLanguage": 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7'
    })
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    })
    return driver

def check_card_status(card_number):
    driver = None
    screenshot_path = f"status_{card_number}.png"
    try:
        driver = get_driver()
        wait = WebDriverWait(driver, 20)
        driver.get(BASE_URL)
        time.sleep(4)

        if "trouver" in driver.page_source or "Accueil" in driver.page_source:
            try:
                accueil_btn = driver.find_element(By.XPATH, "//*[contains(text(), 'Accueil') or contains(text(), 'Home')]")
                driver.execute_script("arguments[0].click();", accueil_btn)
                time.sleep(4)
            except Exception:
                pass

        input_field = wait.until(EC.visibility_of_element_located((By.ID, "f_numero_carte_borne")))
        input_field.clear()
        input_field.send_keys(card_number)

        submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_envoyer")))
        submit_btn.click()

        wait.until(EC.visibility_of_element_located((By.ID, "nomPrenom")))
        driver.save_screenshot(screenshot_path)

        try:
            result_elem = driver.find_element(By.ID, "result")
            final_text = result_elem.text if result_elem.text.strip() else "You have no mail / Vous n'avez pas de courrier"
        except Exception:
            final_text = "You have no mail / Vous n'avez pas de courrier"

        bilingual_text = translate_status(final_text)
        return True, bilingual_text, screenshot_path
    except Exception as e:
        return False, str(e)[:150], None
    finally:
        if driver:
            driver.quit()

def send_status_report(chat_id, card_number, caption_header="📊 **Status / وضعیت:**"):
    success, result, screenshot = check_card_status(card_number)
    try:
        if success and screenshot and os.path.exists(screenshot):
            with open(screenshot, "rb") as photo:
                bot.send_photo(chat_id, photo, caption=f"{caption_header}\n{result}", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, f"❌ Error / خطا:\n{result}")
    finally:
        if screenshot and os.path.exists(screenshot):
            os.remove(screenshot)

# =========================================================
# 4. TELEGRAM BOT HANDLERS
# =========================================================
@bot.message_handler(commands=['start'])
@bot.message_handler(func=lambda message: message.text == "🇦🇫 Welcome")
def send_welcome(message):
    chat_id = str(message.chat.id)
    users = load_users()
    first_name = message.from_user.first_name or "Friend"

    if chat_id in users:
        text = (
            f"🇦🇫 **Salam & Welcome back, {first_name}!** 🇦🇫\n"
            f"خوش آمدید / پخیر راغلاست\n\n"
            f"💳 **Registered Card / شماره کارت شما:** `{users[chat_id]}`\n\n"
            f"Select an option from the menu below:"
        )
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        pending_registration.add(chat_id)
        text = (
            f"🇦🇫 **Salam & Welcome, {first_name}!** 🇦🇫\n"
            f"خوش آمدید / پخیر راغلاست\n\n"
            f"Please enter your **Card Number** to get started:\n"
            f"لطفاً شماره کارت خود را وارد کنید:"
        )
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['update'])
@bot.message_handler(func=lambda message: message.text == "✏️ Update Card")
def update_card(message):
    chat_id = str(message.chat.id)
    pending_registration.add(chat_id)
    bot.reply_to(
        message, 
        "Please enter your new **Card Number** / لطفاً شماره کارت جدید خود را وارد کنید:", 
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['check'])
@bot.message_handler(func=lambda message: message.text == "🔍 Check Status")
def manual_check(message):
    chat_id = str(message.chat.id)
    users = load_users()
    if chat_id not in users:
        bot.reply_to(
            message, 
            "You haven't registered a card number yet! Send /start.\nشما هنوز شماره کارتی ثبت نکرده اید! ارسال /start",
            reply_markup=get_main_keyboard()
        )
        return

    bot.reply_to(message, "🔍 Checking status... / در حال بررسی وضعیت...", reply_markup=get_main_keyboard())
    send_status_report(chat_id, users[chat_id])

@bot.message_handler(commands=['info'])
@bot.message_handler(func=lambda message: message.text == "ℹ️ My Info")
def send_info(message):
    user = message.from_user
    chat_id = str(user.id)
    users = load_users()
    card_number = users.get(chat_id, "Not registered")

    first_name = user.first_name or "N/A"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "None"

    info_text = (
        f"👤 **User Account Info**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"▪️ **Full Name:** {full_name}\n"
        f"▪️ **Username:** {username}\n"
        f"▪️ **User ID:** `{chat_id}`\n"
        f"▪️ **Registered Card:** `{card_number}`\n\n"
        f"🤖 **Bot Status:** Active 🟢"
    )
    bot.send_message(message.chat.id, info_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

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

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text == "❓ Help")
def send_help(message):
    help_text = (
        f"🛠 **Available Commands / راهنما:**\n\n"
        f"• `/start` - Start bot & welcome menu 🇦🇫\n"
        f"• `/check` - Check FTDA card status 🔍\n"
        f"• `/update` - Change registered card number ✏️\n"
        f"• `/info` - View your profile and card details ℹ️\n"
        f"• `/ping` - Check server latency ⚡\n"
        f"• `/help` - Show this menu ❓"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Handle card input registration and unexpected text
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = str(message.chat.id)
    # Ignore button text clicks to avoid saving them as card numbers
    menu_buttons = ["🇦🇫 Welcome", "🔍 Check Status", "✏️ Update Card", "ℹ️ My Info", "⚡ Ping Status", "❓ Help"]
    if message.text in menu_buttons:
        return

    if chat_id in pending_registration:
        card_number = message.text.strip()
        users = load_users()
        users[chat_id] = card_number
        save_users(users)
        pending_registration.remove(chat_id)

        bot.reply_to(
            message, 
            f"✅ Card `{card_number}` saved successfully!\n✅ شماره کارت `{card_number}` ذخیره شد!\n\nChecked automatically every 2 hours.", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        bot.send_message(chat_id, "🔍 Running initial check... / اجرای بررسی اولیه...")
        send_status_report(chat_id, card_number, caption_header="📊 **Initial Status / وضعیت اولیه:**")
    else:
        bot.reply_to(
            message, 
            "Send /start to register or /check to view status.\nبرای ثبت نام /start و برای بررسی /check را بفرستید.",
            reply_markup=get_main_keyboard()
        )

# =========================================================
# 5. BACKGROUND CHECKER LOOP
# =========================================================
def background_checker():
    while True:
        time.sleep(7200) # Check every 2 hours
        users = load_users()
        for chat_id, card_number in users.items():
            try:
                send_status_report(chat_id, card_number, caption_header="⏰ **Automated Update / به‌روزرسانی خودکار**")
            except Exception as e:
                print(f"Background loop error for user {chat_id}: {e}")

# =========================================================
# 6. ENTRY POINT
# =========================================================
if __name__ == "__main__":
    threading.Thread(target=start_health_check_server, daemon=True).start()
    threading.Thread(target=background_checker, daemon=True).start()
    print("🤖 Bilingual Public Telegram Bot Started with Full Selenium Scraper...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
