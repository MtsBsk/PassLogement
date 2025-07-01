import os
import json
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from twilio.rest import Client
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("passlogement_debug.log", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Charger les variables d'environnement
if os.getenv("GITHUB_ACTIONS") != "true":
    load_dotenv()


# URL et fichiers
SITE_URL = 'https://offres.passlogement.com/account'
OLD_OFFERS_FILE = 'old_offers.json'

# Identifiants de connexion
LOGIN_EMAIL = os.getenv('LOGIN_EMAIL')
LOGIN_PASSWORD = os.getenv('LOGIN_PASSWORD')

# Informations Twilio pour l'envoi de SMS
TWILIO_SID = os.getenv('TWILIO_SID')
TWILIO_TOKEN = os.getenv('TWILIO_TOKEN')
TWILIO_PHONE = os.getenv('TWILIO_PHONE')
TO_PHONE = os.getenv('TO_PHONE')

def extract_offers_from_selenium(driver):
    """
    Extrait les offres de logement depuis le navigateur Selenium après chargement complet de la page
    """
    offers = []
    
    try:
        # S'assurer que la page est bien chargée avant de chercher le tableau
        logging.info("Vérification et navigation vers l'onglet des offres...")
        
        # Cliquer sur l'onglet "Les offres" s'il existe - Utilisation de multiples stratégies de sélection
        tab_clicked = False
        
        try:
            # Prendre une capture d'écran avant toute tentative de clic
            driver.save_screenshot('before_menu_click.png')
            logging.info("Capture d'écran avant clic sauvegardée dans 'before_menu_click.png'")
            
            # Stratégie 1: Chercher par le texte exact et la classe CSS basée sur l'image
            try:
                logging.info("Tentative de clic stratégie 1: par texte et classe CSS")
                menu_elements = driver.find_elements(By.CSS_SELECTOR, ".tab > *")
                for element in menu_elements:
                    if "Les offres" in element.text:
                        logging.info(f"Trouvé menu par texte: {element.text}")
                        element.click()
                        tab_clicked = True
                        time.sleep(3)
                        break
            except Exception as e1:
                logging.warning(f"Stratégie 1 échouée: {str(e1)}")
            
            # Stratégie 2: Utiliser la navigation par sélecteurs CSS plus spécifiques
            if not tab_clicked:
                try:
                    logging.info("Tentative de clic stratégie 2: par sélecteur CSS spécifique")
                    
                    # Essai avec le texte exact "Les offres"
                    tabs = driver.find_elements(By.LINK_TEXT, "Les offres")
                    if tabs:
                        tabs[0].click()
                        logging.info("Clic sur l'onglet via LINK_TEXT 'Les offres'")
                        tab_clicked = True
                    else:
                        # Essai avec sélecteur CSS li.tab
                        tabs = driver.find_elements(By.CSS_SELECTOR, "li.tab")
                        if len(tabs) >= 3:  # L'élément "Les offres" est le 3ème tab sur l'image
                            tabs[2].click()
                            logging.info("Clic sur le 3ème onglet")
                            tab_clicked = True
                    
                    # Attendre après le clic
                    time.sleep(5)
                    
                    # Vérifier si un nouveau contenu est apparu (signe que le clic a fonctionné)
                    driver.save_screenshot('after_tab2_click.png')
                except Exception as e2:
                    logging.warning(f"Stratégie 2 échouée: {str(e2)}")
            
            # Stratégie 3: Utiliser JavaScript pour cliquer sur l'élément
            if not tab_clicked:
                try:
                    logging.info("Tentative de clic stratégie 3: par JavaScript")
                    # Exécuter un script JS qui clique sur l'élément avec le texte "Les offres"
                    driver.execute_script("""
                        var elements = document.querySelectorAll('*');
                        for (var i = 0; i < elements.length; i++) {
                            if (elements[i].textContent.includes('Les offres')) {
                                elements[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    logging.info("Tentative de clic via JavaScript")
                    tab_clicked = True
                    time.sleep(3)
                except Exception as e3:
                    logging.warning(f"Stratégie 3 échouée: {str(e3)}")
            
            # Prendre une capture d'écran après la tentative de clic
            driver.save_screenshot('after_menu_click.png')
            logging.info("Capture d'écran après clic sauvegardée dans 'after_menu_click.png'")
            
            if tab_clicked:
                logging.info("Clic sur l'onglet 'Les offres' réussi")
            else:
                logging.warning("Impossible de cliquer sur l'onglet 'Les offres' avec toutes les stratégies")
                
        except Exception as e:
            logging.error(f"Erreur lors de la tentative de clic sur l'onglet 'Les offres': {str(e)}")
            driver.save_screenshot('menu_click_error.png')
        
        # Attendre que le tableau contenant les offres soit chargé
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
        except TimeoutException:
            logging.warning("Aucun tableau trouvé après attente")
        
        # Sauvegarder le contenu HTML après interaction pour débogage
        with open('selenium_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        
        # Extraire toutes les lignes du tableau
        rows = driver.find_elements(By.CSS_SELECTOR, "tr")
        logging.info(f"Nombre de lignes trouvées dans la page: {len(rows)}")
        
        # Prendre une capture d'écran de la page
        driver.save_screenshot('page_screenshot.png')
        logging.info("Capture d'écran sauvegardée dans 'page_screenshot.png'")
        
        # Extraction des données structurées des lignes
        extracted_rows = []
        with open('rows_structured.txt', 'w', encoding='utf-8') as f:
            f.write(f"Nombre total de lignes: {len(rows)}\n\n")
            
            for i, row in enumerate(rows):
                try:
                    # Extraire le texte de chaque cellule dans la ligne
                    cells = row.find_elements(By.TAG_NAME, "td")
                    row_data = {}
                    
                    if len(cells) >= 1:
                        row_text = row.text.strip()
                        f.write(f"\nLIGNE {i+1}: {row_text}\n")
                        
                        # Extraire les valeurs individuelles des cellules
                        cell_values = [cell.text.strip() for cell in cells]
                        f.write("Cellules: " + " | ".join(cell_values) + "\n")
                        
                        # Essayer d'identifier le type de ligne/contenu
                        line_type = "Inconnu"
                        if len(cells) >= 3:
                            if any(keyword in row_text.lower() for keyword in ['t1', 't2', 't3', 't4', 'studio']):
                                line_type = "Offre de logement"
                            elif any(keyword in row_text.lower() for keyword in ['document', 'pdf', 'attestation']):
                                line_type = "Document"
                        
                        f.write(f"Type de ligne identifié: {line_type}\n")
                        f.write("-" * 80 + "\n")
                        
                        # Sauvegarder les données structurées
                        row_data = {
                            "row_num": i+1,
                            "text": row_text,
                            "cells": cell_values,
                            "type": line_type
                        }
                        extracted_rows.append(row_data)
                except Exception as e:
                    f.write(f"Erreur sur ligne {i+1}: {str(e)}\n")
                    
        # Sauvegarde en JSON pour analyse ultérieure
        with open('rows_data.json', 'w', encoding='utf-8') as f:
            json.dump(extracted_rows, f, ensure_ascii=False, indent=4)
        
        # Analyser chaque ligne qui pourrait contenir une offre
        for row in rows:
            try:
                # Trouver toutes les cellules dans cette ligne
                cells = row.find_elements(By.TAG_NAME, "td")
                
                if len(cells) >= 8:  # Vérifier qu'il y a suffisamment de cellules pour les colonnes attendues
                    try:
                        # Extraction des données
                        partenaire = cells[0].text.strip() if cells[0].text else "N/A"
                        reference = cells[1].text.strip() if len(cells) > 1 and cells[1].text else "N/A"
                        departement = cells[2].text.strip() if len(cells) > 2 and cells[2].text else "N/A"
                        ville = cells[3].text.strip() if len(cells) > 3 and cells[3].text else "N/A"
                        type_logement = cells[4].text.strip() if len(cells) > 4 and cells[4].text else "N/A" 
                        surface = cells[5].text.strip() if len(cells) > 5 and cells[5].text else "N/A"
                        loyer = cells[7].text.strip() if len(cells) > 7 and cells[7].text else "N/A"
                        
                        # Vérifier que c'est une offre valide
                        if ville != "N/A" and type_logement != "N/A" and loyer != "N/A":
                            offre = f"{ville} - {surface} - {loyer}"
                            logging.info(f"Offre détectée: {offre}")
                            offers.append(offre)
                    except Exception as e:
                        logging.debug(f"Erreur lors de l'extraction des données de cellule: {str(e)}")
            except Exception as e:
                logging.debug(f"Erreur lors du traitement d'une ligne: {str(e)}")
    
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des offres: {str(e)}")
    
    return offers

def main():
    # Configuration du navigateur Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Mode sans interface graphique
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    logging.info("Initialisation du navigateur Chrome...")
    
    try:
        # Initialisation du navigateur
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_page_load_timeout(30)  # Timeout pour le chargement des pages
        
        # Accès à la page principale
        logging.info(f"Accès à la page: {SITE_URL}")
        driver.get(SITE_URL)
        
        # Attente que la page soit chargée et vérifier si nous sommes déjà sur la page de compte ou si login est nécessaire
        try:
            # Attendre un court moment pour que la page charge
            time.sleep(2)
            
            # Vérifier si on est sur une page de login (chercher les champs email/password)
            login_fields = driver.find_elements(By.NAME, "username")
            
            if login_fields:
                # Nous sommes sur la page de login, entrer les identifiants
                logging.info("Page de login détectée, saisie des identifiants...")
                driver.find_element(By.NAME, "username").send_keys(LOGIN_EMAIL)
                driver.find_element(By.NAME, "password").send_keys(LOGIN_PASSWORD)
                driver.find_element(By.XPATH, "//button[@type='button']").click()
                
                # Attendre la redirection après connexion
                WebDriverWait(driver, 10).until(
                    EC.url_contains("account")
                )
                
                # Attendre un peu plus longtemps pour que la page se charge complètement
                logging.info("Attente de 5 secondes pour que la page se charge complètement après connexion...")
                time.sleep(5)
                
                logging.info(f"Connecté avec succès, URL actuelle: {driver.current_url}")
                
                # Prendre une capture d'écran après connexion
                driver.save_screenshot('after_login.png')
                logging.info("Capture d'écran après connexion sauvegardée dans 'after_login.png'")
            else:
                # Nous sommes déjà sur la page compte/offres
                logging.info("Déjà connecté ou aucun login requis")
                
        except Exception as e:
            logging.error(f"Erreur lors de la vérification/connexion: {str(e)}")
            driver.save_screenshot('login_error.png')
            driver.quit()
            return
        
        # Vérifier qu'on est sur la bonne page
        if SITE_URL not in driver.current_url:
            logging.info(f"Navigation vers la page principale: {SITE_URL}")
            driver.get(SITE_URL)
            time.sleep(2)  # Attendre que la page se charge
        
        # Extraction des offres
        offers = extract_offers_from_selenium(driver)
        logging.info(f"Nombre total d'offres trouvées: {len(offers)}")
        
        # Fermeture du navigateur
        driver.quit()
        
        # Chargement des anciennes offres pour comparaison
        if os.path.exists(OLD_OFFERS_FILE):
            with open(OLD_OFFERS_FILE, 'r', encoding='utf-8') as f:
                try:
                    old_offers = json.load(f)
                except json.JSONDecodeError:
                    logging.warning("Fichier d'anciennes offres corrompu. Création d'une nouvelle liste.")
                    old_offers = []
        else:
            old_offers = []
        
        # Détection des nouvelles offres
        new_offers = [o for o in offers if o not in old_offers]
        logging.info(f"Nombre de nouvelles offres: {len(new_offers)}")
        
        # Envoi SMS si nouveautés et configuration Twilio disponible
        if new_offers and all([TWILIO_SID, TWILIO_TOKEN, TWILIO_PHONE, TO_PHONE]):
            try:
                client = Client(TWILIO_SID, TWILIO_TOKEN)
                body = "Nouvelle(s) offre(s) Pass Logement :\n" + "\n".join(new_offers[:3])
                if len(new_offers) > 3:
                    body += f"\n(+{len(new_offers)-3} autres)"
                
                # Limiter à 1600 caractères max pour SMS
                body = body[:1600]
                
                client.messages.create(
                    body=body,
                    from_=TWILIO_PHONE,
                    to=TO_PHONE
                )
                logging.info(f"SMS envoyé avec {len(new_offers)} nouvelles offres")
            except Exception as e:
                logging.error(f"Erreur lors de l'envoi du SMS: {str(e)}")
        elif new_offers:
            logging.warning("Nouvelles offres trouvées mais configuration Twilio incomplète. SMS non envoyé.")
        else:
            logging.info("Aucune nouvelle offre détectée.")
        
        # Sauvegarde des offres actuelles
        with open(OLD_OFFERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(offers, f, indent=2)
            
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        try:
            # Si le driver existe toujours, le fermer
            if 'driver' in locals() and driver:
                driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
