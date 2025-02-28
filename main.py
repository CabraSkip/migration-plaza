import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
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
from items import migrate_items, migrate_linked_items
import winreg

os.environ['WDM_CACHED_DRIVER_EXPIRY_SEC'] = '86400'  # 24 hours in seconds
DEFAULT_BROWSER = None  # Cache for browser detection

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
    print("    a. Only linked label")
    print("12. Links")
    print("\n------- Extra ----------------------")
    print("r. Return to main menu")
    print("\nTip: You can run multiple features by:")
    print("   - Using commas for individual selections (e.g. 0,1,5)")
    print("   - Using dash for range selections (e.g. 1-5)")
    print("   - Combinations are also supported (e.g. 0,2-5,8,10-12)")
    return input("\nSelect feature(s) to migrate: ")

def check_domain_and_store_availability(domain1, domain2, store1, store2):
    """Check domain and store availability concurrently with shorter timeouts."""
    results = {"domain1": False, "domain2": False, "store1": False, "store2": False}
    session = requests.Session()  # Use a shared session for connection pooling
    
    def check_domain(domain, key):
        try:
            session.head(
                f"https://central-manager.{domain}.pcm.pricer-plaza.com", 
                timeout=2.5  # Shorter timeout
            )
            results[key] = True
        except:
            write_log(f"Error: Domain {domain} does not exist", "red")
    
    def check_store(store, key):
        try:
            response = session.head(
                f"https://{store}.pcm.pricer-plaza.com", 
                timeout=2.5  # Shorter timeout
            )
            if response.status_code in [200, 302]:
                results[key] = True
            else:
                write_log(f"Error: Store {store} is not accessible (status code {response.status_code})", "red")
        except requests.exceptions.RequestException:
            write_log(f"Error: Store {store} is not accessible", "red")
    
    # Create and start all threads
    threads = [
        threading.Thread(target=check_domain, args=(domain1, "domain1")),
        threading.Thread(target=check_domain, args=(domain2, "domain2")),
        threading.Thread(target=check_store, args=(store1, "store1")),
        threading.Thread(target=check_store, args=(store2, "store2"))
    ]
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    # Check results
    domains_ok = results["domain1"] and results["domain2"]
    stores_ok = results["store1"] and results["store2"]
    
    return domains_ok, stores_ok

def get_store_data(domain, auth_token):
    try:
        write_log(f"Fetching store data for domain {domain}...", "cyan")  # Add progress indicator
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/stores",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            },
            timeout=10  # Add timeout to prevent hanging
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

def fetch_store_data_concurrent(domain1, domain2, auth_token1, auth_token2):
    """Fetch store data for both domains concurrently using threads."""
    store_data = {'domain1': None, 'domain2': None}
    
    def fetch_domain1():
        store_data['domain1'] = get_store_data(domain1, auth_token1)
        
    def fetch_domain2():
        store_data['domain2'] = get_store_data(domain2, auth_token2)
    
    # Create and start threads
    thread1 = threading.Thread(target=fetch_domain1)
    thread2 = threading.Thread(target=fetch_domain2)
    
    thread1.start()
    thread2.start()
    
    # Wait for both threads to complete
    thread1.join()
    thread2.join()
    
    return store_data

def get_default_browser(force_detect=False):
    """Detect the user's default web browser on Windows with caching."""
    global DEFAULT_BROWSER
    
    # Return cached browser if available and not forcing detection
    if DEFAULT_BROWSER and not force_detect:
        return DEFAULT_BROWSER
    
    write_log("Detecting default browser...", "cyan")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        
        browser_name = prog_id.lower()
        
        if "chrome" in browser_name:
            DEFAULT_BROWSER = "chrome"
        elif "firefox" in browser_name:
            DEFAULT_BROWSER = "firefox"
        elif "edge" in browser_name:
            DEFAULT_BROWSER = "edge"
        else:
            write_log(f"Detected browser: {browser_name}, defaulting to Chrome", "yellow")
            DEFAULT_BROWSER = "chrome"
    except Exception as e:
        write_log(f"Error detecting default browser: {e}. Defaulting to Chrome", "yellow")
        DEFAULT_BROWSER = "chrome"
    
    write_log(f"Using {DEFAULT_BROWSER} as default browser", "cyan")
    return DEFAULT_BROWSER

def is_browser_debug_session_running(port=9222):
    """Check if there's already a browser debug session running on the specified port."""
    try:
        response = requests.get(f"http://localhost:{port}/json/version", timeout=1)
        return response.status_code == 200
    except:
        return False

def is_firefox_running():
    """Check if Firefox is running."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'firefox' in proc.info['name'].lower():
            return True
    return False

def kill_browser_processes(browser_type):
    """Kill all processes of the specified browser type."""
    browser_exes = {
        "chrome": ["chrome.exe", "chromium.exe"],
        "edge": ["msedge.exe"],
        "firefox": ["firefox.exe"]
    }
    
    if browser_type in browser_exes:
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in browser_exes[browser_type]:
                    proc.kill()
                    write_log(f"Killed {proc.info['name']} process", "yellow")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(1)  # Give processes time to terminate

def try_get_token_from_browser(driver, domain):
    """Try to get authentication token for a domain from browser cookies."""
    try:
        driver.switch_to.window(driver.window_handles[0])
        url = f"https://central-manager.{domain}.pcm.pricer-plaza.com"
        write_log(f"Loading {domain} to retrieve token...", "cyan")  # Add progress indicator
        driver.get(url)
        
        # Use dynamic waiting with the correct method
        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        cookies = driver.get_cookies()
        token_cookie = next((cookie for cookie in cookies if cookie['name'] == 'token'), None)
        
        if token_cookie:
            write_log(f"Domain {domain}: token found: {token_cookie['value'][:20]}...", "green")
            return token_cookie['value']
        
        write_log(f"No token cookie found for domain {domain}", "red")
        return None
        
    except Exception as e:
        write_log(f"Error retrieving token from browser for domain {domain}: {str(e)}", "red")
        return None

def get_auth_token_from_browser(domain1, domain2):
    """Get authentication tokens for both domains using the default browser."""
    browser_type = get_default_browser()
    
    driver = None
    try:
        # Handle different browser types
        if browser_type in ["chrome", "edge"]:
            debug_port = 9222
            debug_session_exists = is_browser_debug_session_running(debug_port)
            
            if not debug_session_exists:
                kill_browser_processes(browser_type)
                if browser_type == "chrome":
                    os.system(f'start chrome --profile-directory="Default" --remote-debugging-port={debug_port}')
                else:  # edge
                    os.system(f'start msedge --profile-directory="Default" --remote-debugging-port={debug_port}')
                time.sleep(3)  # Wait for browser to start
            
            # Connect to the debug session
            if browser_type == "chrome":
                options = ChromeOptions()
                options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
                # Use default cache settings without explicit cache_valid_range
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            else:  # edge
                options = EdgeOptions()
                options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
                # Use default cache settings without explicit cache_valid_range
                service = EdgeService(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=options)
                
        elif browser_type == "firefox":
            options = FirefoxOptions()
            
            # If Firefox is already running, we'll connect to it
            if not is_firefox_running():
                # Start Firefox (Firefox doesn't support remote debugging port like Chrome)
                subprocess.Popen(['firefox', '-new-instance'])
                time.sleep(3)  # Wait for Firefox to start
            
            # Use default cache settings without explicit cache_valid_range
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
        
        # Try to get tokens for both domains
        token1 = try_get_token_from_browser(driver, domain1)
        time.sleep(1)  # Wait between requests
        token2 = try_get_token_from_browser(driver, domain2)
        
        # If tokens couldn't be retrieved, prompt the user
        if not token1:
            write_log(f"Please enter auth token for domain {domain1}:", "cyan")
            token1 = input("Auth Token> ")
            
        if not token2:
            write_log(f"Please enter auth token for domain {domain2}:", "cyan")
            token2 = input("Auth Token> ")
            
        return token1, token2, driver
        
    except Exception as e:
        write_log(f"Unexpected error in browser token retrieval: {e}", "red")
        return None, None, driver

def get_auth_token(domain, store):
    """Deprecated function, kept for backward compatibility."""
    write_log(f"Enter auth token for {store} :", "cyan")
    return input("Auth Token> ")

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
    get_default_browser()  # Pre-detect browser
    while True:
        migration_type = get_migration_type()
        if migration_type != "2":
            write_log("Only Plaza to Plaza migration is currently supported", "red")
            continue

        #store1 = input("Enter source store1_ID.domain1 (e.g. 1017.plus): ")
        #store2 = input("Enter target store2_ID.domain2 (e.g. 6101.plus-v2): ")
        store2 = "demo.ps"
        store1 = "11111.plusa"

        domain1, domain2 = store1.split('.')[1], store2.split('.')[1]

        # Run domain and store checks concurrently
        write_log("Checking domain and store availability...", "cyan")
        domains_ok, stores_ok = check_domain_and_store_availability(domain1, domain2, store1, store2)
        
        if not domains_ok or not stores_ok:
            continue

        auth_token1, auth_token2, driver = get_auth_token_from_browser(domain1, domain2)

        if not all([auth_token1, auth_token2]):
            continue

        STORE_DATA = fetch_store_data_concurrent(domain1, domain2, auth_token1, auth_token2)

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
                elif feature == "11a" or feature == "11.a":
                    if not store1 or not store2 or not auth_token1 or not auth_token2:
                        write_log("Please set source and target stores and authenticate first!", "red")
                    else:
                        write_log(f"Migrating linked items from {store1} to {store2}...", "cyan")
                        migrate_linked_items(store1, store2, auth_token1, auth_token2)
                elif feature == "12":
                    links.migrate_links(store1, store2, auth_token1, auth_token2)

if __name__ == "__main__":
    main()