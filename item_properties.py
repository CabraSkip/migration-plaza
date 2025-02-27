from common import write_log
import requests

def get_item_properties(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/item-properties?filter%5BsystemDefined%5D=false",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting item properties: {str(e)}", "red")
        return None

def create_item_property(store, auth_token, property_data):
    try:
        property_name = property_data['name']
        response = requests.put(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/item-properties/{property_name}",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json={
                "isCustomizable": property_data.get('isCustomizable', True),
                "isSystemDefined": property_data.get('isSystemDefined', False),
                "maxLength": property_data.get('maxLength', 500),
                "name": property_name,
                "pfiId": property_data.get('pfiId', 392),
                "standardItemPropertyMapping": property_data.get('standardItemPropertyMapping', 'notMapped'),
                "type": property_data.get('type', 'STRING')
            }
        )
        response.raise_for_status()
        write_log(f"Successfully created property: {property_name}", "green")
        return True
    except Exception as e:
        write_log(f"Error creating property {property_name}: {str(e)}", "red")
        return False

def migrate_item_properties(store1, store2, auth_token1, auth_token2):
    # Get source properties
    properties = get_item_properties(store1, auth_token1)
    if not properties:
        return False

    success_count = 0
    for prop in properties:
        if create_item_property(store2, auth_token2, prop):
            success_count += 1

    write_log(f"Item properties migration complete. {success_count}/{len(properties)} properties migrated", "green")
    return True