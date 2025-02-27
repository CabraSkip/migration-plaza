from common import write_log
import requests
import json

def get_system_parameters(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/system-parameters",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting system parameters from {store}: {str(e)}", "red")
        return None

def patch_system_parameters(store, auth_token, parameters):
    simplified_params = [
        {
            "name": param["name"],
            "value": param["value"]
        }
        for param in parameters
        if param["name"] not in ["MESSAGE_FILE_PATH", "DEFAULT_RESULT_FILE_PATH", "MYSQL_BIN_PATH", "DATABASE_BACKUP_FULL_FILE_PATH", "DROP_FOLDER_LOCATION", "ROUTE_PLANNING_EXIT_UNIMPROVED_DURATION", "ROUTE_PLANNING_DURATION", ""]
    ]

    try:
        response = requests.patch(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/system-parameters",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=simplified_params
        )
        write_log(f"Response status: {response.status_code}", "cyan")
        write_log(f"Response body: {response.text}", "cyan")
        response.raise_for_status()
        return True
    except Exception as e:
        write_log(f"Error patching system parameters to {store}: {str(e)}", "red")
        return False

def migrate_system_parameters(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting system parameters from {store1}", "cyan")
    parameters = get_system_parameters(store1, auth_token1)
    
    if not parameters:
        write_log("Failed to get system parameters from source store", "red")
        return False

    write_log(f"Found {len(parameters)} parameters in source store", "cyan")
    write_log(f"Patching filtered system parameters to {store2}", "cyan")
    if patch_system_parameters(store2, auth_token2, parameters):
        write_log("System parameters migration completed successfully", "green")
        return True
    else:
        write_log("Failed to patch system parameters to target store", "red")
        return False