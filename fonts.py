from common import write_log
import main
import requests
import os
import tempfile

def get_store_group_id(store_data, store):
    for s in store_data:
        if s['externalId'] == store.split('.')[0]:
            return s['storeGroupId']
    return None

def get_fonts(store_group_id, auth_token, domain):
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting fonts list: {str(e)}", "red")
        return None

def download_font(store_group_id, font_name, auth_token, domain):
    try:
        response = requests.get(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts/{font_name}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response.raise_for_status()
        return response.content
    except Exception as e:
        write_log(f"Error downloading font {font_name}: {str(e)}", "red")
        return None

def upload_font(store_group_id, font_name, font_data, auth_token, domain):
    try:
        files = {'fontFile': (font_name, font_data)}
        response = requests.post(
            f"https://central-manager.{domain}.pcm.pricer-plaza.com/api/private/web/store-groups/{store_group_id}/fonts",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files
        )
        
        if response.status_code == 400:
            error_message = response.text  # Get the error message from response
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
    domain1, domain2 = store1.split('.')[1], store2.split('.')[1]
    
    # Get store group IDs
    source_group_id = get_store_group_id(store_data1, store1)
    target_group_id = get_store_group_id(store_data2, store2)
    
    if not source_group_id or not target_group_id:
        write_log("Could not find store group IDs", "red")
        return False
        
    # Get list of fonts
    fonts = get_fonts(source_group_id, auth_token1, domain1)
    if not fonts:
        write_log("No fonts found in source store", "yellow")
        return False
        
    success_count = 0
    temp_dir = tempfile.mkdtemp()
    
    # Process each font
    for font in fonts:
        font_name = font['filename']
        write_log(f"Processing font: {font_name}", "cyan")
        
        # Download font
        font_data = download_font(source_group_id, font_name, auth_token1, domain1)
        if not font_data:
            continue
            
        # Upload font
        if upload_font(target_group_id, font_name, font_data, auth_token2, domain2):
            success_count += 1
            write_log(f"Successfully migrated font: {font_name}", "green")
        
    write_log(f"Font migration complete. {success_count}/{len(fonts)} fonts migrated successfully", "green")
    return True