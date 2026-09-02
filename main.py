import os
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

# --- HEALTH CHECK SERVER (Required for Render Web Services) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is healthy and running.")

def start_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- BOT CONFIG & DATABASE ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
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

# --- SELENIUM SCRAPER ---
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

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    users = load_users()
    if chat_id in users:
        bot.reply_to(message,
            f"👋 Welcome back! / خوش آمدید!\n"
            f"Your card number / شماره کارت شما: `{users[chat_id]}`\n\n"
            f"Commands / دستورات:\n"
            f"/check - Check status / بررسی وضعیت\n"
            f"/update - Change card / تغییر شماره کارت", parse_mode="Markdown")
    else:
        pending_registration.add(chat_id)
        bot.reply_to(message, "👋 Welcome! Please enter your **Card Number**:\n\n👋 خوش آمدید! لطفاً شماره کارت خود را وارد کنید:", parse_mode="Markdown")

@bot.message_handler(commands=['update'])
def update_card(message):
    chat_id = str(message.chat.id)
    pending_registration.add(chat_id)
    bot.reply_to(message, "Please enter your new **Card Number** / لطفاً شماره کارت جدید خود را وارد کنید:", parse_mode="Markdown")

@bot.message_handler(commands=['check'])
def manual_check(message):
    chat_id = str(message.chat.id)
    users = load_users()
    if chat_id not in users:
        bot.reply_to(message, "You haven't registered a card number yet! Send /start.\nشما هنوز شماره کارتی ثبت نکرده اید! ارسال /start")
        return

    bot.reply_to(message, "🔍 Checking status... / در حال بررسی وضعیت...")
    send_status_report(chat_id, users[chat_id])

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = str(message.chat.id)
    if chat_id in pending_registration:
        card_number = message.text.strip()
        users = load_users()
        users[chat_id] = card_number
        save_users(users)
        pending_registration.remove(chat_id)

        bot.reply_to(message, f"✅ Card `{card_number}` saved successfully!\n✅ شماره کارت `{card_number}` ذخیره شد!\n\nChecked automatically every 2 hours.", parse_mode="Markdown")
        bot.send_message(chat_id, "🔍 Running initial check... / اجرای بررسی اولیه...")
        send_status_report(chat_id, card_number, caption_header="📊 **Initial Status / وضعیت اولیه:**")
    else:
        bot.reply_to(message, "Send /start to register or /check to view status.\nبرای ثبت نام /start و برای بررسی /check را بفرستید.")

def background_checker():
    while True:
        time.sleep(7200)
        users = load_users()
        for chat_id, card_number in users.items():
            try:
                send_status_report(chat_id, card_number, caption_header="⏰ **Automated Update / به‌روزرسانی خودکار**")
            except Exception as e:
                print(f"Background loop error for user {chat_id}: {e}")

if __name__ == "__main__":
    threading.Thread(target=start_health_check_server, daemon=True).start()
    threading.Thread(target=background_checker, daemon=True).start()
    print("🤖 Bilingual Public Telegram Bot Started...")
    bot.infinity_polling()
