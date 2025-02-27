from common import write_log
import requests

def get_esl_config(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/private/esl/v1/config",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting ESL config from {store}: {str(e)}", "red")
        return None

def post_esl_config(store, auth_token, config):
    try:
        response = requests.post(
            f"https://{store}.pcm.pricer-plaza.com/api/private/esl/v1/config",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=config
        )
        response.raise_for_status()
        return True
    except Exception as e:
        write_log(f"Error posting ESL config to {store}: {str(e)}", "red")
        return False

def migrate_templates(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting ESL configuration from {store1}", "cyan")
    config = get_esl_config(store1, auth_token1)
    
    if not config:
        write_log("Failed to get ESL configuration from source store", "red")
        return False
        
    write_log(f"Posting ESL configuration to {store2}", "cyan")
    if post_esl_config(store2, auth_token2, config):
        write_log("Templates migration completed successfully", "green")
        return True
    else:
        write_log("Failed to post ESL configuration to target store", "red")
        return False