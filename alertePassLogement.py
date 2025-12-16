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
    handlers=[logging.StreamHandler()]
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

REQUIRED_VARS = [
    "LOGIN_EMAIL",
    "LOGIN_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

# =========================
# TELEGRAM
# =========================
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_notification": False
    }
    requests.post(url, json=payload, timeout=10)


def click_offers_tab(driver):
    logging.info("Tentative de clic sur l’onglet 'Les offres'")

    try:
        tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'Les offres')]")
        if tabs:
            driver.execute_script("arguments[0].click();", tabs[0])
            time.sleep(3)
            logging.info("Onglet 'Les offres' cliqué")
            return True
    except Exception as e:
        logging.warning(f"Impossible de cliquer sur l’onglet : {e}")

    return False

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

            texts = [c.text.strip() for c in cells]

            # Vérifier qu'il y a un loyer ou le symbole € pour filtrer les lignes pertinentes
            if any("€" in t for t in texts):
                # Extraire les informations principales avec fallback si la colonne est absente
                partenaire = texts[0] if len(texts) > 0 else "N/A"
                reference = texts[1] if len(texts) > 1 else "N/A"
                departement = texts[2] if len(texts) > 2 else "N/A"
                ville = texts[3] if len(texts) > 3 else "N/A"
                type_logement = texts[4] if len(texts) > 4 else "N/A"
                surface = texts[5] if len(texts) > 5 else "N/A"
                loyer = texts[7] if len(texts) > 7 else "N/A"

                # Créer le message formaté
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
    chrome_options.add_argument("user-agent=PassLogementWatcher/1.0 (contact: LOGIN_EMAIL)")

    
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

        click_offers_tab(driver)
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
        msg += "\n".join(new_offers)


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
