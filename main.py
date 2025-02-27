import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from common import write_log
import threading
import queue
import requests
from datetime import datetime
import infrastructure
import fonts
import item_properties
import os
import psutil
import time
import images
import globalparameters
import templates
import webhooks
import systemparameters
import generalsettings
import jobs
import geoloc
import items
import links

CHALLENGES = {
    'plusa': "Basic cGx1c2FAbWlncmF0aW9uLm5sOlByaWNlcjEh",
    'plus': "Basic cGx1c0BtaWdyYXRpb24ubmw6UHJpY2VyMSE=",
    'plus-v2-acc': "Basic cGx1cy12Mi1hY2NAbWlncmF0aW9uLm5sOlByaWNlcjEh",
    'plus-v2': "Basic cGx1cy12MkBtaWdyYXRpb24ubmw6UHJpY2VyMSE=",
    'ps': "Basic bWlncmF0aW9uQHBzLmZyOlByaWNlcjEh"
}

def get_migration_type():
    print("\n1. Onprem to Plaza migration")
    print("2. Plaza to Plaza migration")
    return input("Select migration type (1-2): ")

def get_migration_feature():
    print("\n------- Generic configuration ------")
    print("0. Fonts")
    print("1. Item properties")
    print("2. Images (Files)")
    print("3. Global parameter")
    print("4. Templates")
    print("5. Webhooks")
    print("6. System parameter")
    print("7. General settings")
    print("\n------- Store specific settings ----")
    print("8. Jobs")
    print("9. Geoloc")
    print("\n------- Store pecific datas --------")
    print("10. Infra + Trx position")
    print("11. Items")
    print("12. Links")
    print("\n------- Extra ----------------------")
    print("r. Return to main menu")
    print("\nTip: You can run multiple features by:")
    print("   - Using commas for individual selections (e.g. 0,1,5)")
    print("   - Using dash for range selections (e.g. 1-5)")
    print("   - Combinations are also supported (e.g. 0,2-5,8,10-12)")
    return input("\nSelect feature(s) to migrate: ")

def check_domain_availability(domain):
    try:
        requests.head(f"https://central-manager.{domain}.pcm.pricer-plaza.com")
        return True
    except:
        write_log(f"Error: Domain {domain} does not exist", "red")
        return False

def check_store_availability(store):
    try:
        response = requests.head(f"https://{store}.pcm.pricer-plaza.com", timeout=5)
        if response.status_code in [200, 302]:
            return True
        write_log(f"Error: Store {store} is not accessible (status code {response.status_code})", "red")
        return False
    except requests.exceptions.RequestException:
        write_log(f"Error: Store {store} is not accessible", "red")
        return False

def get_auth_token(domain, store):
    if domain not in CHALLENGES:
        write_log(f"Enter auth token for {store} :", "cyan")
        return input("Auth Token> ")
    
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/public/auth/v1/login",
            headers={"Authorization": CHALLENGES[domain]},
            timeout=30
        )
        token = response.json()["token"]
        write_log(f"Successfully retrieved token for {store} via challenge method", "green")
        return token
    except Exception as e:
        write_log(f"Error getting auth token: {str(e)}", "red")
        return None

def get_store_data(domain, auth_token):
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/stores",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        if response.status_code == 200:
            write_log(f"Successfully retrieved store data for domain {domain}", "green")
            return response.json()
        else:
            write_log(f"Failed to get store data for domain {domain}: {response.status_code}", "red")
            return None
    except Exception as e:
        write_log(f"Error getting store data for domain {domain}: {str(e)}", "red")
        return None

def try_chrome_token(driver, domain):
    try:
        driver.switch_to.window(driver.window_handles[0])
        url = f"https://central-manager.{domain}.pcm.pricer-plaza.com"
        driver.get(url)
        time.sleep(1)  # Wait for page load
        
        cookies = driver.get_cookies()
        token_cookie = next((cookie for cookie in cookies if cookie['name'] == 'token'), None)
        
        if token_cookie:
            write_log(f"Domain {domain} : token found: {token_cookie['value'][:20]}...", "green")
            return token_cookie['value']
            
        write_log("No token cookie found", "red")
        return None
        
    except Exception as e:
        write_log(f"Error: {str(e)}", "red")
        return None

def get_auth_token_from_browser(domain1, domain2):
    driver = None
    try:
        # Initial Chrome launch with timeout
        os.system('taskkill /F /IM chrome.exe')
        
        # Use a thread to launch Chrome with timeout
        chrome_thread = threading.Event()
        chrome_launched = threading.Event()
        
        def launch_chrome():
            try:
                os.system('start chrome --profile-directory="Default" --remote-debugging-port=9222')
                chrome_launched.set()
            except Exception as e:
                write_log(f"Chrome launch error: {e}", "red")
            finally:
                chrome_thread.set()
        
        launch_thread = threading.Thread(target=launch_chrome)
        launch_thread.start()
        
        # Wait for Chrome to launch or timeout
        if not chrome_launched.wait(timeout=15):
            write_log("Chrome failed to launch within 15 seconds", "red")
            return None, None, None
        
        # Wait a bit to ensure Chrome is fully up
        time.sleep(1)
        
        chrome_options = ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        chrome_options.add_argument("--remote-allow-origins=*")
        
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Get tokens for both domains with timeouts
        def get_token_with_timeout(domain):
            try:
                with threading.Lock():
                    token_queue = queue.Queue()
                    
                    def token_retrieval():
                        try:
                            token = try_chrome_token(driver, domain)
                            token_queue.put(token)
                        except Exception as e:
                            write_log(f"Token retrieval error for {domain}: {e}", "red")
                            token_queue.put(None)
                    
                    retrieval_thread = threading.Thread(target=token_retrieval)
                    retrieval_thread.daemon = True
                    retrieval_thread.start()
                    
                    return token_queue.get(timeout=15)
            except queue.Empty:
                write_log(f"Token retrieval timed out for {domain}", "red")
                return None

        token1 = get_token_with_timeout(domain1)
        time.sleep(1)  # Wait between requests
        token2 = get_token_with_timeout(domain2)

        # Fallback to get_auth_token if Selenium token retrieval fails
        if not token1:
            write_log(f"Falling back to get_auth_token for {domain1}", "yellow")
            token1 = get_auth_token(domain1, domain1)
        
        if not token2:
            write_log(f"Falling back to get_auth_token for {domain2}", "yellow")
            token2 = get_auth_token(domain2, domain2)

        return token1, token2, driver

    except Exception as e:
        write_log(f"Unexpected error in browser token retrieval: {e}", "red")
        return None, None, driver
    finally:
        # Ensure driver is closed if it was opened
        if driver:
            try:
                driver.quit()
            except:
                pass

def parse_feature_input(feature_input):
    """Parse feature input that may contain ranges and/or individual selections."""
    if feature_input.lower() == 'a':
        return [str(i) for i in range(8)]  # 0 to 7
    
    features = []
    segments = feature_input.split(',')
    
    for segment in segments:
        segment = segment.strip()
        
        # Check if it's a range (e.g., "1-5")
        if '-' in segment:
            try:
                start, end = segment.split('-')
                start, end = int(start.strip()), int(end.strip())
                features.extend([str(i) for i in range(start, end + 1)])
            except ValueError:
                write_log(f"Invalid range format: {segment}. Skipping this segment.", "red")
        # Individual option
        else:
            if segment:  # Only add non-empty segments
                features.append(segment)
    
    return features
    			 
def main():
    while True:
        migration_type = get_migration_type()
        if migration_type != "2":
            write_log("Only Plaza to Plaza migration is currently supported", "red")
            continue  # Changed from return to continue

        #store1 = input("Enter source store1_ID.domain1 (e.g. 1017.plus): ")
        #store2 = input("Enter target store2_ID.domain2 (e.g. 6101.plus-v2): ")
        store2 = "demo.ps"
        store1 = "11111.plusa"

        domain1, domain2 = store1.split('.')[1], store2.split('.')[1]

        if not all(check_domain_availability(d) for d in [domain1, domain2]):
            continue  # Changed from return to continue

        if not all(check_store_availability(s) for s in [store1, store2]):
            continue  # Changed from return to continue

        auth_token1, auth_token2, driver = get_auth_token_from_browser(domain1, domain2)
        if driver:
            driver.quit()

        if not all([auth_token1, auth_token2]):
            continue

        STORE_DATA = {'domain1': None, 'domain2': None}
        STORE_DATA['domain1'] = get_store_data(domain1, auth_token1)
        STORE_DATA['domain2'] = get_store_data(domain2, auth_token2)

        if not all([STORE_DATA['domain1'], STORE_DATA['domain2']]):
            write_log("Failed to retrieve store data for one or both domains", "red")
            continue  # Changed from return to continue

        while True:
            feature_input = get_migration_feature()
            if feature_input.lower() == "r":
                break  # Break inner loop to return to migration type selection
                
            features = parse_feature_input(feature_input)
                
            for feature in features:
                feature = feature.strip()
                if feature == "0":
                    fonts.migrate_fonts(store1, store2, auth_token1, auth_token2, STORE_DATA['domain1'], STORE_DATA['domain2'])
                elif feature == "1":
                    item_properties.migrate_item_properties(store1, store2, auth_token1, auth_token2)
                elif feature == "2":
                    images.migrate_images(store1, store2, auth_token1, auth_token2)
                elif feature == "3":
                    globalparameters.migrate_global_parameters(store1, store2, auth_token1, auth_token2)
                elif feature == "4":
                    templates.migrate_templates(store1, store2, auth_token1, auth_token2)
                elif feature == "5":
                    webhooks.migrate_webhooks(store1, store2, auth_token1, auth_token2)
                elif feature == "6":
                    systemparameters.migrate_system_parameters(store1, store2, auth_token1, auth_token2)
                elif feature == "7":
                    generalsettings.migrate_web_settings(store1, store2, auth_token1, auth_token2)
                elif feature == "8":
                    jobs.migrate_jobs(store1, store2, auth_token1, auth_token2)
                elif feature == "9":
                    geoloc.migrate_geoloc(store1, store2, auth_token1, auth_token2)
                elif feature == "10":
                    infrastructure.migrate_infrastructure(store1, store2, auth_token1, auth_token2, STORE_DATA['domain2'])
                elif feature == "11":
                    items.migrate_items(store1, store2, auth_token1, auth_token2)
                elif feature == "12":
                    links.migrate_links(store1, store2, auth_token1, auth_token2)

if __name__ == "__main__":
    main()