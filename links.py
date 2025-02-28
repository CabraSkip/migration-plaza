import requests
import json
import time
from common import write_log
from tqdm import tqdm

def get_links(store, auth_token):
    """
    Get all links from the specified store using the labels API
    """
    write_log(f"Fetching links from {store}...", "cyan")
    try:
        url = f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/labels?projection=M&start=0&limit=200000&serializeDatesToIso8601=true"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            write_log(f"Failed to get links: {response.status_code} - {response.text}", "red")
            return None
        
        data = response.json()
        write_log(f"Successfully fetched {len(data)} links from {store}", "green")
        return data
    
    except Exception as e:
        write_log(f"Error getting links: {str(e)}", "red")
        return None

def upload_links(store, auth_token, links_data):
    """
    Upload links to the specified store using the labels API
    """
    write_log(f"Uploading links to {store}...", "cyan")
    try:
        url = f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/labels"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
        
        response = requests.patch(url, headers=headers, json=links_data)
        
        if response.status_code != 200:
            write_log(f"Failed to upload links: {response.status_code} - {response.text}", "red")
            return False
        
        write_log(f"Successfully uploaded links to {store}", "green")
        return True
    
    except Exception as e:
        write_log(f"Error uploading links: {str(e)}", "red")
        return False

def clean_link_data(link):
    """
    Clean and prepare link data for migration by removing unwanted properties
    """
    # Remove properties that shouldn't be migrated !
    if "batteryState" in link:
        del link["batteryState"]
    
    if "plState" in link:
        del link["plState"]
    
    return link

def migrate_links(store1, store2, auth_token1, auth_token2):
    """
    Migrate links from store1 to store2
    """
    write_log(f"\n--- Starting links migration from {store1} to {store2} ---", "yellow")
    
    # Get links from source store
    links_data = get_links(store1, auth_token1)
    
    if not links_data:
        write_log("No links found or error fetching links", "red")
        return False
    
    # Count the links
    total_links = len(links_data)
    write_log(f"Found {total_links} links to migrate", "green")
    
    if total_links == 0:
        write_log("No links to migrate", "yellow")
        return False
    
    # Clean links data - remove unwanted properties
    cleaned_links = []
    for link in tqdm(links_data, desc="Processing links"):
        cleaned_links.append(clean_link_data(link))
    
    # Upload links to target store
    write_log(f"Uploading {len(cleaned_links)} links to {store2}...", "cyan")
    upload_result = upload_links(store2, auth_token2, cleaned_links)
    
    if upload_result:
        write_log("\n--- Links Migration Summary ---", "yellow")
        write_log(f"Total links processed: {total_links}", "cyan")
        write_log(f"Successfully migrated: {total_links}", "green")
        return True
    else:
        write_log("\n--- Links Migration Failed ---", "red")
        return False
