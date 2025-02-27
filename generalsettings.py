from common import write_log
import requests
import json

def get_general_settings(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/general-settings",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting general settings from {store}: {str(e)}", "red")
        return None

def patch_general_settings(store, auth_token, settings):
    simplified_settings = [
        {
            "name": setting["name"],
            "value": setting["value"]
        }
        for setting in settings
    ]

    try:
        response = requests.patch(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/general-settings",
            headers={
                "accept": "*/*", 
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=simplified_settings
        )
        write_log(f"Response status: {response.status_code}", "cyan")
        write_log(f"Response body: {response.text}", "cyan")
        response.raise_for_status()
        return True
    except Exception as e:
        write_log(f"Error patching general settings to {store}: {str(e)}", "red")
        return False

def migrate_web_settings(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting general settings from {store1}", "cyan")
    settings = get_general_settings(store1, auth_token1)

    if not settings:
        write_log("Failed to get general settings from source store", "red")
        return False

    write_log(f"Found {len(settings)} settings in source store", "cyan")
    write_log(f"Patching general settings to {store2}", "cyan")
    if patch_general_settings(store2, auth_token2, settings):
        write_log("General settings migration completed successfully", "green")
        return True
    else:
        write_log("Failed to patch general settings to target store", "red")
        return False