from common import write_log
from endpoint_handler import endpoint_handler
import requests
import tempfile
import os

def get_store_group_id(store_data, store):
    """Get store group ID from store data, safely handling None case."""
    if not store_data:
        write_log("Store data is None", "yellow")
        return None
        
    try:
        # Get store ID from the store parameter
        store_id = store.split('.')[0]
        write_log(f"Looking for store group ID for store '{store_id}' in {len(store_data)} store records", "cyan")
        
        # Look for the store in the data
        for store_record in store_data:
            if store_record.get('externalId') == store_id:
                group_id = store_record.get('storeGroupId')
                write_log(f"Found store group ID: {group_id}", "green")
                return group_id
                
        # If we get here, we didn't find a match
        write_log(f"Could not find store {store_id} in store data", "yellow")
        
    except Exception as e:
        write_log(f"Error extracting store group ID: {str(e)}", "red")
    
    return None

def get_store_group_id_direct(domain, auth_token):
    """Get store group ID directly via API call."""
    try:
        write_log(f"Attempting to fetch store groups directly from API", "cyan")
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        response.raise_for_status()
        store_groups = response.json()
        
        if store_groups and len(store_groups) > 0:
            # Print available store groups to help debug
            for sg in store_groups:
                write_log(f"Available store group: ID={sg.get('id')}, Name={sg.get('name')}", "cyan")
                
            # Return the first store group ID if available
            group_id = store_groups[0].get('id')
            write_log(f"Using first available store group ID: {group_id}", "green")
            return group_id
        else:
            write_log("No store groups found", "yellow")
    except Exception as e:
        write_log(f"Error fetching store groups: {str(e)}", "red")
    
    return None

def is_onprem(store):
    """Determine if a store is onprem based on its format."""
    return not "." in store or ":" in store

def get_fonts_onprem(store, auth):
    """Get fonts from onprem server."""
    try:
        url = endpoint_handler.get_full_url("store1", "/api/public/file/v1/fonts")
        headers = endpoint_handler.get_headers("store1")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        # Convert response to expected format - onprem returns [{name: "font.ttf"}, ...] 
        fonts_list = response.json()
        write_log(f"Found {len(fonts_list)} fonts on onprem server", "green")
        return fonts_list
    except Exception as e:
        write_log(f"Error getting fonts from onprem: {str(e)}", "red")
        return None

def get_fonts_plaza(domain, store_group_id, auth_token):
    """Get fonts from Plaza server."""
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response.raise_for_status()
        write_log(f"Found {len(response.json())} fonts on Plaza server", "green")
        return response.json()
    except Exception as e:
        write_log(f"Error getting fonts from Plaza: {str(e)}", "red")
        return None

def download_font_onprem(font_name, auth):
    """Download font from onprem server."""
    try:
        url = endpoint_handler.get_full_url("store1", f"/api/public/file/v1/fonts/{font_name}")
        headers = endpoint_handler.get_headers("store1")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.content
    except Exception as e:
        write_log(f"Error downloading font {font_name} from onprem: {str(e)}", "red")
        return None

def download_font_plaza(domain, store_group_id, font_name, auth_token):
    """Download font from Plaza server."""
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts/{font_name}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response.raise_for_status()
        return response.content
    except Exception as e:
        write_log(f"Error downloading font {font_name} from Plaza: {str(e)}", "red")
        return None

def upload_font_plaza(domain, store_group_id, font_name, font_data, auth_token):
    """Upload font to Plaza server."""
    try:
        files = {'fontFile': (font_name, font_data)}
        response = requests.post(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files
        )
        
        if response.status_code == 400:
            error_message = response.text
            if "File name is invalid" in error_message:
                write_log(f"Error uploading font {font_name}: Invalid filename", "red")
            elif "Font already exists" in error_message:
                write_log(f"Skipping font {font_name}: Already exists in target store", "yellow")
            else:
                write_log(f"Error uploading font {font_name}: {error_message}", "red")
            return False
            
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        write_log(f"Network error uploading font {font_name}: {str(e)}", "red")
        return False
    except Exception as e:
        write_log(f"Unexpected error uploading font {font_name}: {str(e)}", "red")
        return False

def migrate_fonts(store1, store2, auth_token1, auth_token2, store_data1, store_data2):
    """Migrate fonts from store1 to store2, handling both onprem and Plaza sources."""
    source_is_onprem = is_onprem(store1)
    
    if source_is_onprem:
        # For Onprem to Plaza
        write_log("Migrating fonts from Onprem to Plaza...", "cyan")
        fonts_list = get_fonts_onprem(store1, auth_token1)
        
        # Get target store group ID
        domain2 = store2.split('.')[1]
        
        # Debug: Print store_data2 to see its content
        if store_data2:
            write_log(f"Retrieved store_data2 with {len(store_data2)} records", "green")
            for i, store in enumerate(store_data2):
                write_log(f"Store {i+1}: id={store.get('id')}, externalId={store.get('externalId')}, storeGroupId={store.get('storeGroupId')}", "cyan")
        else:
            write_log("store_data2 is None - check if it's being correctly passed to this function", "red")
                
        target_group_id = get_store_group_id(store_data2, store2)
        
        if not target_group_id:
            write_log("CRITICAL: Could not find target store group ID. Migration will fail.", "red")
            return False
            
    else:
        # For Plaza to Plaza
        domain1, domain2 = store1.split('.')[1], store2.split('.')[1]
        
        # Get store group IDs (for Plaza to Plaza)
        source_group_id = get_store_group_id(store_data1, store1)
        target_group_id = get_store_group_id(store_data2, store2)
        
        if not source_group_id or not target_group_id:
            write_log("Could not find store group IDs, using store IDs as fallback", "yellow")
            source_group_id = source_group_id or store1.split('.')[0]
            target_group_id = target_group_id or store2.split('.')[0]
            
        # Get list of fonts from Plaza source
        fonts_list = get_fonts_plaza(domain1, source_group_id, auth_token1)
    
    # Check if we got any fonts
    if not fonts_list or len(fonts_list) == 0:
        write_log("No fonts found in source store", "yellow")
        return False
        
    write_log(f"Found {len(fonts_list)} fonts to migrate", "green")
    success_count = 0
    
    # Process each font
    for font in fonts_list:
        # Handle different response formats
        font_name = font.get('filename', font.get('name', None))
        if not font_name:
            write_log(f"Error: Could not determine font name from {font}", "red")
            continue
            
        write_log(f"Processing font: {font_name}", "cyan")
        
        # Download font using appropriate method
        if source_is_onprem:
            font_data = download_font_onprem(font_name, auth_token1)
        else:
            font_data = download_font_plaza(domain1, source_group_id, font_name, auth_token1)
            
        if not font_data:
            write_log(f"Failed to download font {font_name}", "red")
            continue
            
        # Upload font to Plaza target
        if upload_font_plaza(domain2, target_group_id, font_name, font_data, auth_token2):
            success_count += 1
            write_log(f"Successfully migrated font: {font_name}", "green")
        
    write_log(f"Font migration complete. {success_count}/{len(fonts_list)} fonts migrated successfully", "green")
    return True