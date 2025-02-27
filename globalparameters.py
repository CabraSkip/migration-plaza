from common import write_log
import requests

def get_global_parameters(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/global-parameters",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting global parameters from {store}: {str(e)}", "red")
        return None

def patch_global_parameters(store, auth_token, parameters):
    try:
        # Transform parameters from GET to PATCH format
        patch_data = []
        for param in parameters:
            patch_data.append({
                "key": param["name"],
                "value": param["value"]
            })

        response = requests.patch(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/global-parameters",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=patch_data
        )
        response.raise_for_status()
        return True
    except Exception as e:
        write_log(f"Error patching global parameters to {store}: {str(e)}", "red")
        return False

def migrate_global_parameters(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting global parameters from {store1}", "cyan")
    parameters = get_global_parameters(store1, auth_token1)
    
    if not parameters:
        write_log("Failed to get global parameters from source store", "red")
        return False
        
    write_log(f"Patching {len(parameters)} global parameters to {store2}", "cyan")
    if patch_global_parameters(store2, auth_token2, parameters):
        write_log("Global parameters migration completed successfully", "green")
        return True
    else:
        write_log("Failed to patch global parameters to target store", "red")
        return False