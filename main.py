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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from common import write_log
import threading
import requests
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
from endpoint_handler import endpoint_handler
import winreg
import base64
import re
import socket

os.environ['WDM_CACHED_DRIVER_EXPIRY_SEC'] = '86400'  # 24 hours in seconds
DEFAULT_BROWSER = None  # Cache for browser detection
MIGRATION_TYPE = None  # Global to track migration type

def get_migration_type():
    global MIGRATION_TYPE
    print("\n1. Onprem to Plaza migration")
    print("2. Plaza to Plaza migration")
    migration_type = input("Select migration type (1-2): ")
    MIGRATION_TYPE = migration_type
    return migration_type

def parse_onprem_address(address):
    """Parse an onprem address into host and port."""
    if not address:
        return "127.0.0.1", 3333
        
    if ":" in address:
        host, port_str = address.split(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            port = 3333
    else:
        host = address
        port = 3333
        
    if not host:
        host = "127.0.0.1"
        
    return host, port

def check_onprem_availability(address):
    """Check if onprem server is available with different protocols and ports."""
    host, port = parse_onprem_address(address)
    
    # Try different combinations
    variants = [
        (host, port, False),  # http with original port
        (host, port, True),   # https with original port
    ]
    
    # If port is 3333, also try 3336
    if port == 3333:
        variants.append((host, 3336, True))  # https with port 3336
    
    for test_host, test_port, is_https in variants:
        protocol = "https" if is_https else "http"
        url = f"{protocol}://{test_host}:{test_port}"
        
        try:
            write_log(f"Testing connection to {url}...", "cyan")
            response = requests.head(f"{url}", timeout=3)
            
            if response.status_code < 400:  # Any success or redirect status
                write_log(f"Successfully connected to {url}", "green")
                # Return the working configuration
                return True, test_host, test_port, is_https
                
        except Exception as e:
            write_log(f"Connection to {url} failed: {str(e)}", "yellow")
    
    write_log(f"Could not connect to onprem server at {host}:{port}", "red")
    return False, host, port, False

def check_onprem_api_compatibility(host, port, is_https, auth_header):
    """Check which APIs are available on the onprem server."""
    protocol = "https" if is_https else "http"
    base_url = f"{protocol}://{host}:{port}"
    
    # Updated API paths for onprem compatibility
    apis = {
        "fonts": "/api/public/file/v1/fonts",
        "item_properties": "/api/public/config/v1/item-properties",
        "images": "/api/public/file/v1/image-folder",
        "global_parameters": "/api/public/config/v1/global-parameters",
        "templates": "/api/private/esl/v1/config",
        "webhooks": "/api/public/config/v1/webhook/configurations",
        "system_parameters": "/api/public/config/v1/system-parameters",
        "general_settings": "/api/public/config/v1/general-settings",
        "jobs": "/api/public/config/v1/jobs",
        "geoloc": "/api/public/map/v1/geo-store/floors",
        # Updated these API paths to use core/v1 instead of config/v1
        "infrastructure": "/api/public/infra/v1/basestations",
        "items": "/api/public/core/v1/items", 
        "links": "/api/public/core/v1/labels"
    }
    
    compatibility = {}
    headers = {"Authorization": auth_header}
    
    for api_name, api_path in apis.items():
        try:
            url = f"{base_url}{api_path}"
            write_log(f"Checking API: {url}", "cyan")
            
            # Try HEAD first
            try:
                response = requests.head(url, headers=headers, timeout=5)
                available = response.status_code < 400
            except:
                # If HEAD fails, try GET
                try:
                    response = requests.get(url, headers=headers, timeout=5)
                    available = response.status_code < 400
                except:
                    available = False
                    
            compatibility[api_name] = available
            status = "Available" if available else "Not available"
            write_log(f"API {api_name}: {status}", "green" if available else "red")
            
        except Exception as e:
            compatibility[api_name] = False
            write_log(f"Error checking {api_name} API: {str(e)}", "red")
    
    return compatibility

def get_onprem_auth(host, port, is_https):
    """Try to authenticate with onprem server."""
    protocol = "https" if is_https else "http"
    base_url = f"{protocol}://{host}:{port}"
    
    # Hardcoded challenges to try first
    challenges = [
        "Y29uZmlnOkMwfFx8ZiFn",  # config:C0|\|f!g
        "Y29uZmlnOmNvbmZpZw=="   # config:config
    ]
    
    for challenge in challenges:
        auth_header = f"Basic {challenge}"
        try:
            response = requests.get(
                f"{base_url}/api/public/config/v1/templates/presentations",
                headers={"Authorization": auth_header},
                timeout=5
            )
            if response.status_code == 200:
                write_log("Successfully authenticated with hardcoded credentials", "green")
                return auth_header
        except:
            pass
    
    # If hardcoded challenges fail, ask for credentials
    write_log("Hardcoded credentials failed, please enter login credentials", "yellow")
    username = input("Username: ")
    password = input("Password: ")
    
    # Create Base64 challenge
    auth_string = f"{username}:{password}"
    auth_bytes = auth_string.encode('ascii')
    base64_bytes = base64.b64encode(auth_bytes)
    base64_auth = base64_bytes.decode('ascii')
    
    auth_header = f"Basic {base64_auth}"
    
    # Verify the credentials
    try:
        response = requests.get(
            f"{base_url}/api/public/config/v1/templates/presentations",
            headers={"Authorization": auth_header},
            timeout=5
        )
        if response.status_code == 200:
            write_log("Successfully authenticated with provided credentials", "green")
            return auth_header
        else:
            write_log("Authentication failed with provided credentials", "red")
            return None
    except Exception as e:
        write_log(f"Error authenticating: {str(e)}", "red")
        return None

def check_domain_and_store_availability(domain1, domain2, store1, store2):
    """Check domain and store availability concurrently with shorter timeouts."""
    global MIGRATION_TYPE
    
    if (MIGRATION_TYPE == "1"):  # Onprem to Plaza
        # First check onprem availability
        onprem_available, onprem_host, onprem_port, onprem_https = check_onprem_availability(address=store1)
        
        # Then check Plaza domain/store using the simpler approach
        results = {"domain2": False, "store2": False}
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
        
        # Start threads for plaza checks
        threads = [
            threading.Thread(target=check_domain, args=(domain2, "domain2")),
            threading.Thread(target=check_store, args=(store2, "store2"))
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Register endpoint for onprem if available
        if onprem_available:
            global_store1 = f"{onprem_host}:{onprem_port}"
            endpoint_handler.register_endpoint(
                "store1", 
                global_store1, 
                is_https=onprem_https, 
                auth_type="basic",
                auth_value=None  # Will be set after authentication
            )
        
        # Return combined result
        all_ok = onprem_available and results["domain2"] and results["store2"]
        return all_ok, onprem_host, onprem_port, onprem_https, None
    
    else:  # Plaza to Plaza - use the simple implementation
        results = {"domain1": False, "domain2": False, "store1": False, "store2": False}
        session = requests.Session()
        
        def check_domain(domain, key):
            try:
                session.head(
                    f"https://central-manager.{domain}.pcm.pricer-plaza.com", 
                    timeout=2.5
                )
                results[key] = True
            except:
                write_log(f"Error: Domain {domain} does not exist", "red")
        
        def check_store(store, key):
            try:
                response = session.head(
                    f"https://{store}.pcm.pricer-plaza.com", 
                    timeout=2.5
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
        
        # Get combined result and return with extra None values to maintain function signature
        domains_stores_ok = results["domain1"] and results["domain2"] and results["store1"] and results["store2"]
        return domains_stores_ok, None, None, None, None

def get_migration_feature(api_compatibility=None):
    print("\n------- Generic configuration ------")
    print("0. Fonts" + (" - API not available" if api_compatibility and not api_compatibility.get("fonts", True) else ""))
    print("1. Item properties" + (" - API not available" if api_compatibility and not api_compatibility.get("item_properties", True) else ""))
    print("2. Images (Files)" + (" - API not available" if api_compatibility and not api_compatibility.get("images", True) else ""))
    print("3. Global parameter" + (" - API not available" if api_compatibility and not api_compatibility.get("global_parameters", True) else ""))
    print("4. Templates" + (" - API not available" if api_compatibility and not api_compatibility.get("templates", True) else ""))
    print("5. Webhooks" + (" - API not available" if api_compatibility and not api_compatibility.get("webhooks", True) else ""))
    print("6. System parameter" + (" - API not available" if api_compatibility and not api_compatibility.get("system_parameters", True) else ""))
    print("7. General settings" + (" - API not available" if api_compatibility and not api_compatibility.get("general_settings", True) else ""))
    print("\n------- Store specific settings ----")
    print("8. Jobs" + (" - API not available" if api_compatibility and not api_compatibility.get("jobs", True) else ""))
    print("9. Geoloc" + (" - API not available" if api_compatibility and not api_compatibility.get("geoloc", True) else ""))
    print("\n------- Store pecific datas --------")
    print("10. Infra + Trx position" + (" - API not available" if api_compatibility and not api_compatibility.get("infrastructure", True) else ""))
    print("11. Items" + (" - API not available" if api_compatibility and not api_compatibility.get("items", True) else ""))
    print("    a. Only linked label" + (" - API not available" if api_compatibility and not api_compatibility.get("items", True) else ""))
    print("12. Links" + (" - API not available" if api_compatibility and not api_compatibility.get("links", True) else ""))
    print("\n------- Extra ----------------------")
    print("r. Return to main menu")
    print("\nTip: You can run multiple features by:")
    print("   - Using commas for individual selections (e.g. 0,1,5)")
    print("   - Using dash for range selections (e.g. 1-5)")
    print("   - Combinations are also supported (e.g. 0,2-5,8,10-12)")
    return input("\nSelect feature(s) to migrate: ")

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
    threads = []
    
    def fetch_domain(domain, auth_token, key):
        store_data[key] = get_store_data(domain, auth_token)
    
    # Create threads with proper exception handling
    threads.append(threading.Thread(target=fetch_domain, args=(domain1, auth_token1, 'domain1')))
    threads.append(threading.Thread(target=fetch_domain, args=(domain2, auth_token2, 'domain2')))
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
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
    except requests.exceptions.RequestException:
        # Catch any request exception, including timeouts
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
    if not driver:
        write_log(f"No driver instance available for domain {domain}", "red")
        return None
        
    try:
        # Check if driver has window handles available
        if len(driver.window_handles) == 0:
            write_log(f"No browser windows available for domain {domain}", "red")
            return None
            
        # Make sure we're on the first window
        driver.switch_to.window(driver.window_handles[0])
        
        # Add timeout to page load
        driver.set_page_load_timeout(20)
        
        url = f"https://central-manager.{domain}.pcm.pricer-plaza.com"
        write_log(f"Loading {domain} to retrieve token...", "cyan")
        
        try:
            driver.get(url)
        except Exception as e:
            write_log(f"Error loading page: {str(e)}", "red")
            # Try to continue anyway
        
        # Use dynamic waiting with the correct method
        try:
            wait = WebDriverWait(driver, 5)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            write_log("Timed out waiting for page to load, trying to continue...", "yellow")
        
        # Get cookies even if page load had problems
        cookies = driver.get_cookies()
        token_cookie = next((cookie for cookie in cookies if cookie['name'] == 'token'), None)
        
        if token_cookie and token_cookie['value']:
            masked_value = token_cookie['value'][:10] + "..." if len(token_cookie['value']) > 10 else token_cookie['value']
            write_log(f"Domain {domain}: token found: {masked_value}", "green")
            return token_cookie['value']
        
        write_log(f"No token cookie found for domain {domain}", "red")
        return None
        
    except Exception as e:
        write_log(f"Error retrieving token from browser for domain {domain}: {str(e)}", "red")
        return None

def get_auth_token_from_browser(domain1, domain2):
    """Get authentication tokens for both domains using the default browser - EXACT copy from plazatoplazamain.py."""
    global MIGRATION_TYPE
    browser_type = get_default_browser()
    
    driver = None
    try:
        # Handle different browser types
        if browser_type in ["chrome", "edge"]:
            debug_port = 9222
            debug_session_exists = is_browser_debug_session_running(debug_port)
            
            if not debug_session_exists:
                kill_browser_processes(browser_type)
                browser_cmd = 'chrome' if browser_type == "chrome" else 'msedge'
                write_log(f"Starting {browser_cmd} with remote debugging port...", "cyan")
                os.system(f'start {browser_cmd} --profile-directory="Default" --remote-debugging-port={debug_port}')
                time.sleep(3)  # Wait for browser to start
            
            # Connect to the debug session
            options = ChromeOptions() if browser_type == "chrome" else EdgeOptions()
            options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
            
            # Use appropriate service
            if browser_type == "chrome":
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            else:  # edge
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
        
        # Get tokens depending on migration type
        if MIGRATION_TYPE == "1":  # Onprem to Plaza
            token1 = "N/A"  # No token needed for onprem
            token2 = try_get_token_from_browser(driver, domain2)
        else:  # Plaza to Plaza
            token1 = try_get_token_from_browser(driver, domain1)
            time.sleep(1)  # Wait between requests
            token2 = try_get_token_from_browser(driver, domain2)
        
        # If tokens couldn't be retrieved, prompt the user
        if MIGRATION_TYPE != "1" and not token1:
            write_log(f"Please enter auth token for domain {domain1}:", "cyan")
            token1 = input("Auth Token> ")
            
        if not token2:
            write_log(f"Please enter auth token for domain {domain2}:", "cyan")
            token2 = input("Auth Token> ")
            
        return token1, token2, driver
        
    except Exception as e:
        write_log(f"Unexpected error in browser token retrieval: {e}", "red")
        # Fallback to manual input without trying to quit driver
        if MIGRATION_TYPE != "1":
            write_log(f"Please enter auth token for domain {domain1}:", "cyan")
            token1 = input("Auth Token> ")
        else:
            token1 = "N/A"
            
        write_log(f"Please enter auth token for domain {domain2}:", "cyan")
        token2 = input("Auth Token> ")
            
        return token1, token2, driver

def get_plaza_token_direct(domain):
    """Get a token for a Plaza domain directly via user input, skipping browser automation."""
    write_log(f"Please enter auth token for domain {domain}:", "cyan")
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
    global MIGRATION_TYPE
    get_default_browser()  # Pre-detect browser
    while True:
        MIGRATION_TYPE = get_migration_type()
        
        if MIGRATION_TYPE == "1":  # Onprem to Plaza
            store1 = input("Enter onprem server address (IP:port, default 127.0.0.1:3333): ")
            store2 = input("Enter target store2_ID.domain2 (e.g. 6101.plus-v2): ")
            
            try:
                domain2 = store2.split('.')[1]
            except IndexError:
                write_log("Invalid store format for Plaza store. Please use format storeID.domain", "red")
                continue
            
            domain1 = "onprem"  # Placeholder for onprem
            
            # Check connections
            write_log("Checking onprem and Plaza store availability...", "cyan")
            connections_ok, onprem_host, onprem_port, onprem_https, _ = check_domain_and_store_availability(
                domain1, domain2, store1, store2
            )
            
            if not connections_ok:
                continue
            
            # Define STORE_DATA at the start to avoid reference errors
            STORE_DATA = {'domain2': None}
            
            # Get auth for onprem
            auth_header1 = get_onprem_auth(onprem_host, onprem_port, onprem_https)
            if not auth_header1:
                write_log("Failed to authenticate with onprem server", "red")
                continue
            
            # Extract the base64 part safely
            try:
                # Make sure auth_header1 is a string and contains the expected format
                if not isinstance(auth_header1, str):
                    raise ValueError("Invalid auth header format")
                    
                auth_value = auth_header1.split(' ')[1] if ' ' in auth_header1 else auth_header1
                
                # Register and update the endpoint with auth
                store1 = f"{onprem_host}:{onprem_port}"
                endpoint_handler.register_endpoint(
                    "store1", 
                    store1, 
                    is_https=onprem_https, 
                    auth_type="basic",
                    auth_value=auth_value
                )
            except Exception as e:
                write_log(f"Error registering onprem endpoint: {str(e)}", "red")
                continue
                
            # Check API compatibility
            api_compatibility = check_onprem_api_compatibility(
                onprem_host, onprem_port, onprem_https, auth_header1
            )
            
            # For Plaza store, get auth token using browser first, then fallback to direct input
            auth_token1, auth_token2, driver = get_auth_token_from_browser(domain1, domain2)
            
            # For onprem migration, auth_token1 should be "N/A", so we only care about auth_token2
            if not auth_token2:
                write_log("Failed to get token for Plaza store", "red")
                continue
                
            try:
                # Register Plaza endpoint
                endpoint_handler.register_endpoint(
                    "store2", 
                    f"{store2}.pcm.pricer-plaza.com", 
                    is_https=True, 
                    auth_type="bearer",
                    auth_value=auth_token2
                )
            except Exception as e:
                write_log(f"Error registering Plaza endpoint: {str(e)}", "red")
                continue
                
            # For onprem to Plaza, we only need the Plaza store data - FETCH ONLY ONCE
            try:
                store_data2 = get_store_data(domain2, auth_token2)
                STORE_DATA['domain2'] = store_data2
                if not store_data2:
                    write_log("Warning: Could not fetch store data for target domain", "yellow")
            except Exception as e:
                write_log(f"Error fetching store data: {e}", "yellow")
                STORE_DATA['domain2'] = None
                
            while True:
                feature_input = get_migration_feature(api_compatibility)
                if feature_input.lower() == "r":
                    break  # Break inner loop to return to migration type selection
                    
                features = parse_feature_input(feature_input)
                
                for feature in features:
                    feature = feature.strip()
                    
                    # Skip features that aren't compatible with this onprem version
                    feature_api_map = {
                        "0": "fonts", "1": "item_properties", "2": "images",
                        "3": "global_parameters", "4": "templates", "5": "webhooks",
                        "6": "system_parameters", "7": "general_settings", "8": "jobs",
                        "9": "geoloc", "10": "infrastructure", "11": "items", 
                        "11a": "items", "11.a": "items", "12": "links"
                    }
                    
                    if feature in feature_api_map and not api_compatibility.get(feature_api_map[feature], False):
                        write_log(f"Feature {feature} is not available in this onprem version", "red")
                        continue
                    
                    if feature == "0":
                        fonts.migrate_fonts(store1, store2, auth_header1, auth_token2, None, STORE_DATA['domain2'])
                    elif feature == "1":
                        item_properties.migrate_item_properties(store1, store2, auth_header1, auth_token2)
                    elif feature == "2":
                        images.migrate_images(store1, store2, auth_header1, auth_token2)
                    elif feature == "3":
                        globalparameters.migrate_global_parameters(store1, store2, auth_header1, auth_token2)
                    elif feature == "4":
                        templates.migrate_templates(store1, store2, auth_header1, auth_token2)
                    elif feature == "5":
                        webhooks.migrate_webhooks(store1, store2, auth_header1, auth_token2)
                    elif feature == "6":
                        systemparameters.migrate_system_parameters(store1, store2, auth_header1, auth_token2)
                    elif feature == "7":
                        generalsettings.migrate_web_settings(store1, store2, auth_header1, auth_token2)
                    elif feature == "8":
                        jobs.migrate_jobs(store1, store2, auth_header1, auth_token2)
                    elif feature == "9":
                        geoloc.migrate_geoloc(store1, store2, auth_header1, auth_token2)
                    elif feature == "10":
                        infrastructure.migrate_infrastructure(store1, store2, auth_header1, auth_token2, STORE_DATA.get('domain2'))
                    elif feature == "11":
                        items.migrate_items(store1, store2, auth_header1, auth_token2)
                    elif feature == "11a" or feature == "11.a":
                        if not store1 or not store2 or not auth_header1 or not auth_token2:
                            write_log("Please set source and target stores and authenticate first!", "red")
                        else:
                            write_log(f"Migrating linked items from {store1} to {store2}...", "cyan")
                            migrate_linked_items(store1, store2, auth_header1, auth_token2)
                    elif feature == "12":
                        links.migrate_links(store1, store2, auth_header1, auth_token2)
        else:  # Plaza to Plaza (original logic)
            store1 = input("Enter source store1_ID.domain1 (e.g. 1017.plus): ")
            store2 = input("Enter target store2_ID.domain2 (e.g. 6101.plus-v2): ")

            try:
                domain1, domain2 = store1.split('.')[1], store2.split('.')[1]
            except IndexError:
                write_log("Invalid store format. Please use format storeID.domain", "red")
                continue

            # Run domain and store checks concurrently
            write_log("Checking domain and store availability...", "cyan")
            domains_stores_ok, _, _, _, _ = check_domain_and_store_availability(domain1, domain2, store1, store2)
            
            if not domains_stores_ok:
                continue

            # Define STORE_DATA at the start to avoid reference errors
            STORE_DATA = {'domain1': None, 'domain2': None}
            
            auth_token1, auth_token2, driver = get_auth_token_from_browser(domain1, domain2)

            # For Plaza to Plaza, we need both tokens
            if not auth_token1:
                write_log(f"Failed to get token for source domain {domain1}", "red")
                continue
                
            if not auth_token2:
                write_log(f"Failed to get token for target domain {domain2}", "red")
                continue
            
            try:
                # Register endpoints for Plaza to Plaza
                endpoint_handler.register_endpoint(
                    "store1", 
                    f"{store1}.pcm.pricer-plaza.com", 
                    is_https=True, 
                    auth_type="bearer",
                    auth_value=auth_token1
                )
                
                endpoint_handler.register_endpoint(
                    "store2", 
                    f"{store2}.pcm.pricer-plaza.com", 
                    is_https=True, 
                    auth_type="bearer",
                    auth_value=auth_token2
                )
            except Exception as e:
                write_log(f"Error registering Plaza endpoints: {str(e)}", "red")
                continue
                
            # Fetch store data after successful token retrieval
            try:
                STORE_DATA = fetch_store_data_concurrent(domain1, domain2, auth_token1, auth_token2)
                
                if not STORE_DATA['domain1']:
                    write_log(f"Warning: Could not fetch store data for source domain {domain1}", "yellow")
                
                if not STORE_DATA['domain2']:
                    write_log(f"Warning: Could not fetch store data for target domain {domain2}", "yellow")
                    
                if not STORE_DATA['domain1'] and not STORE_DATA['domain2']:
                    write_log("Failed to retrieve store data for both domains", "red")
                    if input("Continue anyway? (y/n): ").lower() != 'y':
                        continue
            except Exception as e:
                write_log(f"Error fetching store data: {str(e)}", "yellow")
                if input("Continue anyway? (y/n): ").lower() != 'y':
                    continue
            
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