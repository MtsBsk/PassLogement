import os
import json
import time
import logging
import requests
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("passlogement.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# =========================
# ENV
# =========================
if os.getenv("GITHUB_ACTIONS") != "true":
    load_dotenv()

LOGIN_EMAIL = os.getenv("LOGIN_EMAIL")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SITE_URL = "https://offres.passlogement.com/account"
OLD_OFFERS_FILE = "old_offers.json"

# =========================
# TELEGRAM
# =========================
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    requests.post(url, json=payload, timeout=10)

# =========================
# EXTRACTION OFFRES
# =========================
def extract_offers(driver):
    offers = []

    try:
        logging.info("Recherche du tableau d'offres...")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )

        rows = driver.find_elements(By.CSS_SELECTOR, "tr")

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")

            if len(cells) >= 8:
                ville = cells[3].text.strip()
                departement = cells[2].text.strip()
                type_logement = cells[4].text.strip()
                surface = cells[5].text.strip()
                loyer = cells[7].text.strip()

                if ville and loyer:
                    offer = f"{ville} ({departement}) - {type_logement} - {surface} - {loyer}"
                    offers.append(offer)

    except TimeoutException:
        logging.warning("Aucune offre trouvée (timeout tableau)")

    return offers

# =========================
# MAIN
# =========================
def main():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    try:
        logging.info("Ouverture du site...")
        driver.get(SITE_URL)
        time.sleep(2)

        # LOGIN
        if driver.find_elements(By.NAME, "username"):
            logging.info("Connexion...")
            driver.find_element(By.NAME, "username").send_keys(LOGIN_EMAIL)
            driver.find_element(By.NAME, "password").send_keys(LOGIN_PASSWORD)
            driver.find_element(By.XPATH, "//button").click()

            WebDriverWait(driver, 15).until(
                EC.url_contains("account")
            )
            time.sleep(3)

        # EXTRACTION
        offers = extract_offers(driver)
        logging.info(f"{len(offers)} offres détectées")

    finally:
        driver.quit()

    # LOAD OLD
    if os.path.exists(OLD_OFFERS_FILE):
        with open(OLD_OFFERS_FILE, "r", encoding="utf-8") as f:
            old_offers = json.load(f)
    else:
        old_offers = []

    # DIFF
    new_offers = [o for o in offers if o not in old_offers]

    # NOTIFY
    if new_offers and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        msg = "🏠 *Nouvelles offres Pass Logement*\n\n"
        msg += "\n".join(new_offers[:5])

        if len(new_offers) > 5:
            msg += f"\n\n(+{len(new_offers) - 5} autres)"

        send_telegram_message(msg)
        logging.info("Notification Telegram envoyée")
    else:
        logging.info("Aucune nouvelle offre")

    # SAVE
    with open(OLD_OFFERS_FILE, "w", encoding="utf-8") as f:
        json.dump(offers, f, ensure_ascii=False, indent=2)

# =========================
if __name__ == "__main__":
    main()
