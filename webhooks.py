from common import write_log
import requests

def get_webhook_configurations(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/webhook/configurations",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting webhook configurations from {store}: {str(e)}", "red")
        return None

def create_webhook_configuration(store, auth_token, config):
    # Remove uuid as it's not needed for POST
    if "uuid" in config:
        del config["uuid"]
        
    try:
        response = requests.post(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/webhook/configurations",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=config
        )
        response.raise_for_status()
        write_log(f"Successfully created webhook {config['name']}", "green")
        return True
    except Exception as e:
        write_log(f"Error creating webhook {config['name']}: {str(e)}", "red")
        return False

def migrate_webhooks(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting webhook configurations from {store1}", "cyan")
    configs = get_webhook_configurations(store1, auth_token1)
    
    if not configs:
        write_log("No webhook configurations found in source store", "yellow")
        return False

    success_count = 0
    for config in configs:
        if create_webhook_configuration(store2, auth_token2, config):
            success_count += 1

    write_log(f"Webhook migration complete. {success_count}/{len(configs)} webhooks migrated", "green")
    return True