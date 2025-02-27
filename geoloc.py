from common import write_log
import requests

def check_geoloc_config(store, auth_token, floor_id=0):
    try:
        # Check if at least one of graphical.png or blueprint.png exists
        found_one = False
        for image_type in ['graphical', 'blueprint']:
            response = requests.get(
                f"https://{store}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors/{floor_id}/{image_type}.png",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            if response.status_code in range(200, 300):
                found_one = True
                write_log(f"Found {image_type}.png configuration on {store}", "green")
            else:
                write_log(f"No {image_type}.png found on {store}", "yellow")

        if not found_one:
            write_log(f"No Geoloc configuration found on {store} (neither graphical.png nor blueprint.png exist)", "red")
            return False
            
        return True
    except Exception as e:
        write_log(f"Error checking geoloc config: {str(e)}", "red")
        return False

def get_floors(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting floors: {str(e)}", "red")
        return None

def migrate_image_data(store1, store2, auth_token1, auth_token2, floor_id, image_type):
    try:
        # Get image from source
        get_response = requests.get(
            f"https://{store1}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors/{floor_id}/{image_type}.png",
            headers={"Authorization": f"Bearer {auth_token1}"}
        )
        get_response.raise_for_status()
        
        # Post image to target
        files = {'image': (f'{image_type}.png', get_response.content, 'image/png')}
        post_response = requests.post(
            f"https://{store2}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors/{floor_id}/{image_type}.png",
            headers={"Authorization": f"Bearer {auth_token2}"},
            files=files
        )
        post_response.raise_for_status()
        write_log(f"Successfully migrated {image_type} for floor {floor_id}", "green")
        return True
    except Exception as e:
        write_log(f"Error migrating {image_type}: {str(e)}", "red")
        return False

def migrate_json_data(store1, store2, auth_token1, auth_token2, floor_id, endpoint):
    try:
        # Get data from source
        get_response = requests.get(
            f"https://{store1}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors/{floor_id}/{endpoint}",
            headers={"Authorization": f"Bearer {auth_token1}"}
        )
        get_response.raise_for_status()
        data = get_response.json()
        
        # Put data to target
        put_response = requests.put(
            f"https://{store2}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/floors/{floor_id}/{endpoint}",
            headers={
                "Authorization": f"Bearer {auth_token2}",
                "Content-Type": "application/json"
            },
            json=data
        )
        put_response.raise_for_status()
        write_log(f"Successfully migrated {endpoint} for floor {floor_id}", "green")
        return True
    except Exception as e:
        write_log(f"Error migrating {endpoint}: {str(e)}", "red")
        return False

def migrate_shelf_length(store1, store2, auth_token1, auth_token2):
    try:
        # Get shelf length from source
        get_response = requests.get(
            f"https://{store1}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/default-shelf-length",
            headers={"Authorization": f"Bearer {auth_token1}"}
        )
        get_response.raise_for_status()
        length = get_response.json()
        
        # Put shelf length to target
        put_response = requests.put(
            f"https://{store2}.pcm.pricer-plaza.com/api/public/map/v1/geo-store/default-shelf-length",
            headers={
                "Authorization": f"Bearer {auth_token2}",
                "Content-Type": "application/json"
            },
            json=length
        )
        put_response.raise_for_status()
        write_log("Successfully migrated default shelf length", "green")
        return True
    except Exception as e:
        write_log(f"Error migrating shelf length: {str(e)}", "red")
        return False

def migrate_geoloc(store1, store2, auth_token1, auth_token2):
    write_log(f"Starting geo-store migration from {store1} to {store2}", "cyan")
    
    # Check geoloc configuration exists
    if not check_geoloc_config(store1, auth_token1):
        return False

    # Get floors from source store
    floors = get_floors(store1, auth_token1)
    if not floors:
        return False

    # Process each floor
    for floor in floors:
        floor_id = floor.get("floor", 0)
        write_log(f"Processing floor {floor_id}", "cyan")

        # Migrate images first
        for image_type in ['graphical', 'blueprint']:
            if not migrate_image_data(store1, store2, auth_token1, auth_token2, floor_id, image_type):
                return False

        # Migrate JSON data
        for endpoint in ['obstacles', 'graphical-map-layer', 'floor-boundary', 'blueprint-map-layer']:
            if not migrate_json_data(store1, store2, auth_token1, auth_token2, floor_id, endpoint):
                return False

    # Migrate shelf length
    if not migrate_shelf_length(store1, store2, auth_token1, auth_token2):
        return False

    write_log("Geo-store migration completed successfully", "green")
    write_log("Then, once \"10. Infra + Trx position\" do these tasks manually to complete geoloc migration :", "red")
    write_log("Set Entry/Exit point, check Blueprint /graphical used map, Save+Publish and run \"CAS storeUUID migration\" via qpi.pricer.com", "red")
    return True