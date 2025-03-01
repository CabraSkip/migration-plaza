from common import write_log
from endpoint_handler import endpoint_handler
import requests
import json
from datetime import datetime, timedelta
import time
import queue
import threading

def get_input_with_timeout(prompt, timeout):
    input_queue = queue.Queue()
    
    def input_thread():
        try:
            user_input = input(prompt).strip()
            input_queue.put(user_input)
        except Exception as e:
            input_queue.put(None)
            print(f"Input error: {e}")
    
    thread = threading.Thread(target=input_thread)
    thread.daemon = True
    thread.start()
    
    try:
        return input_queue.get(timeout=timeout)
    except queue.Empty:
        return None

def get_bs_secret(hardware_id, bs_list_file="DuplicateInfra_BS&secret_list.txt"):
    try:
        with open(bs_list_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                parts = line.split(';')
                
                # Check all parts including the first one
                for part in parts:
                    # Check if this part contains a hardware ID/secret pair
                    if '/' in part:
                        try:
                            bs_id, secret = part.split('/')
                            if bs_id.strip() == hardware_id.strip():
                                write_log(f"Found secret for basestation {hardware_id}", "green")
                                return secret.strip()
                        except ValueError:
                            continue
    except Exception as e:
        write_log(f"Error reading secret file: {str(e)}", "red")

    write_log(f"Please enter secret for basestation {hardware_id} (timeout in 2 minutes):", "cyan")
    secret = get_input_with_timeout("Secret> ", 120)
    if secret:
        write_log(f"Secret '{secret}' entered manually for basestation {hardware_id}", "green")
        return secret
    write_log("No secret entered within timeout, script ends", "red")
    return None

def get_basestations(store, auth_token):
    is_onprem = not "." in store or ":" in store
    
    if is_onprem:
        url = endpoint_handler.get_full_url("store1", "/api/public/infra/v1/basestations")
        headers = endpoint_handler.get_headers("store1")
        response = requests.get(url, headers=headers)
    else:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/basestations",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
        )
    return response.json()

def get_link_departments(store, auth_token):
    is_onprem = not "." in store or ":" in store
    
    if is_onprem:
        url = endpoint_handler.get_full_url("store1", "/api/public/infra/v1/link-departments")
        headers = endpoint_handler.get_headers("store1")
        response = requests.get(url, headers=headers)
    else:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/link-departments",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
        )
    return response.json()

def delete_basestation(store, auth_token, bs_name):
    try:
        response = requests.delete(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/basestations/{bs_name}",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        write_log(f"{store} : Basestation {bs_name} deleted - Status: {response.status_code}", "green")
    except Exception as e:
        write_log(f"{store} : Error deleting basestation {bs_name}: {str(e)}", "red")

def delete_link_departments(store, auth_token, departments):
    non_backoffice = [d for d in departments if not d.get('isBackoffice')]
    backoffice = next((d for d in departments if d.get('isBackoffice')), None)

    for dept in non_backoffice:
        try:
            response = requests.delete(
                f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/link-departments/{dept['id']}",
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {auth_token}"
                }
            )
            write_log(f"{store} : Department {dept['id']} deleted - Status: {response.status_code}", "green")
        except Exception as e:
            write_log(f"{store} : Error deleting department {dept['id']}: {str(e)}", "red")

    if backoffice:
        try:
            response = requests.delete(
                f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/link-departments/{backoffice['id']}",
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {auth_token}"
                }
            )
            write_log(f"{store} : Backoffice department deleted - Status: {response.status_code}", "green")
        except Exception as e:
            write_log(f"{store} : Error deleting backoffice department: {str(e)}", "red")

def add_basestation_to_store(bs_hardware_id, secret, store, store_data):
    store_uuid = None
    for s in store_data:
        if s['externalId'] == store.split('.')[0]:
            store_uuid = s['storeUuid']
            break
    
    if not store_uuid:
        write_log(f"Error: Could not find UUID for store {store}", "red")
        return False
    
    domain = store.split('.')[1]
    
    data = {
        'hwid': bs_hardware_id,
        'secret': secret,
        'serverurl': f"bs-{store_uuid}.{domain}.pcm.pricer-plaza.com"
    }
    
    try:
        response = requests.post(
            "https://serverurl.infraconfig.pricer-plaza.com/serverurl.php",
            data=data,
            timeout=30,
            verify=True
        )
        response.raise_for_status()

        if "Invalid HWID" in response.text:
            write_log(f"Error: Invalid hardware ID format for BS {bs_hardware_id}", "red")
            return False
        if "Invalid secret" in response.text:
            write_log(f"Error: Invalid secret format for BS {bs_hardware_id}", "red")
            return False
        
        write_log(f"Add BS {bs_hardware_id} Status: {response.status_code}", "green")
        return True
    
    except requests.exceptions.SSLError:
        write_log(f"SSL Certificate verification failed for BS {bs_hardware_id}", "red")
        return False
    except requests.exceptions.ConnectionError:
        write_log(f"Connection error adding BS {bs_hardware_id}", "red")
        return False
    except requests.exceptions.Timeout:
        write_log(f"Connection timeout adding BS {bs_hardware_id}", "red")
        return False
    except requests.exceptions.RequestException as e:
        write_log(f"Error adding BS {bs_hardware_id}: {str(e)}", "red")
        return False
    
def create_link_department(store, auth_token, dept_data):
    try:
        response = requests.put(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/link-departments/{dept_data['id']}",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json={
                "alias": "",
                "basestationName": dept_data['id'][0],
                "isBackoffice": dept_data['isBackoffice'],
                "transceivers": dept_data['transceivers']
            }
        )
        write_log(f"Created department {dept_data['id']} - Status: {response.status_code}", "green")
        return True
    except Exception as e:
        write_log(f"Error creating department {dept_data['id']}: {str(e)}", "red")
        return False

def wait_for_basestation_status(store, auth_token, bs_hardware_id, target_status, timeout_minutes=10):
    timeout = datetime.now() + timedelta(minutes=timeout_minutes)
    
    while datetime.now() < timeout:
        try:
            response = requests.get(
                f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/basestations",
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            
            if response.status_code != 200:
                write_log(f"Error fetching basestation status: HTTP {response.status_code}", "red")
                time.sleep(15)
                continue
            
            bs_list = response.json()
            current_bs = next((b for b in bs_list if b["hardwareId"] == bs_hardware_id), None)
            
            if current_bs and current_bs["detailedStatus"] == target_status:
                return True
            
            write_log(f"{bs_hardware_id} status: {current_bs['detailedStatus'] if current_bs else 'Not found'}")
            time.sleep(15)
        
        except requests.exceptions.Timeout:
            write_log(f"Timeout checking basestation {bs_hardware_id} status", "red")
            return False
        except Exception as e:
            write_log(f"Error checking basestation status: {str(e)}", "red")
            time.sleep(15)
    
    write_log(f"Timeout waiting for {target_status} status", "red")
    return False

def migrate_basestations(source_bs, store2, auth_token2, bs_secrets):
    write_log(f"Starting migration for {len(source_bs)} basestations to {store2}", "cyan")
    
    for bs in source_bs:
        write_log(f"Processing basestation {bs['hardwareId']}", "cyan")

        if not wait_for_basestation_status(store2, auth_token2, bs['hardwareId'], "CONNECTED"):
            write_log(f"Failed to connect basestation {bs['hardwareId']}, MIGRATION ABORTED", "red")
            return False

        try:
            accept_data = {
                "name": bs["name"],
                "hwId": bs["hardwareId"],
                "transmissionZone": bs.get("transmissionZone", "Main Store")
            }
            response = requests.post(
                f"https://{store2}.pcm.pricer-plaza.com/api/public/infra/v1/basestations/commands/accept",
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {auth_token2}",
                    "Content-Type": "application/json"
                },
                json=accept_data
            )
            if response.status_code not in [200, 201, 204]:
                write_log(f"{store2} : Failed to accept basestation {bs['hardwareId']}", "red")
                return False
            write_log(f"{store2} : Basestation {bs['hardwareId']} accepted with zone {accept_data['transmissionZone']}", "green")
        except Exception as e:
            write_log(f"{store2} : Error accepting basestation {bs['hardwareId']}: {str(e)}", "red")
            return False
    
    for bs in source_bs:
        if not wait_for_basestation_status(store2, auth_token2, bs['hardwareId'], "IRREADY"):
            write_log(f"{store2} : Failed to ready basestation {bs['hardwareId']}", "red")
            return False
        write_log(f"{store2} : Basestation {bs['hardwareId']} ready", "green")

    write_log(f"{store2} : All basestations migrated successfully", "green")
    return True

def recreate_linkdpt(store2, auth_token2, source_link_depts):
    dept_groups = {}
    for dept in source_link_depts:
        first_letter = dept['id'][0]
        if first_letter not in dept_groups:
            dept_groups[first_letter] = []
        dept_groups[first_letter].append(dept)

    for bs_letter, depts in dept_groups.items():
        backoffice_id = f"{bs_letter}01"
        backoffice = next((d for d in depts if d['id'] == backoffice_id), None)
        if backoffice:
            backoffice['isBackoffice'] = True
            if not create_link_department(store2, auth_token2, backoffice):
                write_log(f"Failed to create backoffice department {backoffice_id}", "red")
                return False

        other_depts = [d for d in depts if d['id'] != backoffice_id]
        for dept in other_depts:
            if not create_link_department(store2, auth_token2, dept):
                write_log(f"Failed to create department {dept['id']}", "red")
                return False

    return True

def restore_backoffice(store2, auth_token2, source_link_depts):
    try:
        current_link_depts = get_link_departments(store2, auth_token2)
        original_backoffice = next((d for d in source_link_depts if d.get('isBackoffice')), None)
        current_backoffice = next((d for d in current_link_depts if d.get('isBackoffice')), None)

        if original_backoffice and current_backoffice and original_backoffice['id'] != current_backoffice['id']:

            bs_letter = original_backoffice['id'][0]
            restore_data = {
                "alias": "",
                "basestationName": bs_letter,
                "isBackoffice": True,
                "transceivers": original_backoffice['transceivers']
            }

            response = requests.put(
                f"https://{store2}.pcm.pricer-plaza.com/api/public/infra/v1/link-departments/{original_backoffice['id']}",
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {auth_token2}",
                    "Content-Type": "application/json"
                },
                json=restore_data
            )
            write_log(f"Backoffice restored to {original_backoffice['id']}", "green")
            return True
        else:
            write_log("Backoffice linkdpt already ok", "green")
            return True
    except Exception as e:
        write_log(f"Error handling backoffice configuration: {str(e)}", "red")
        return False

def verify_final_configuration(source_bs, source_link_depts, final_bs, final_link_depts):
    missing_depts = [d['id'] for d in source_link_depts if d['id'] not in [fd['id'] for fd in final_link_depts]]
    extra_depts = [d['id'] for d in final_link_depts if d['id'] not in [sd['id'] for sd in source_link_depts]]
    missing_bs = [b['hardwareId'] for b in source_bs if b['hardwareId'] not in [fb['hardwareId'] for fb in final_bs]]
    extra_bs = [b['hardwareId'] for b in final_bs if b['hardwareId'] not in [sb['hardwareId'] for sb in source_bs]]

    if not (missing_depts or extra_depts or missing_bs or extra_bs):
        write_log("Infrastructure migration completed successfully", "green")
        return True

    if any([missing_depts, extra_depts, missing_bs, extra_bs]):
        if missing_depts: write_log(f"Missing departments: {missing_depts}", "red")
        if extra_depts: write_log(f"Extra departments: {extra_depts}", "red")
        if missing_bs: write_log(f"Missing basestations: {missing_bs}", "red")
        if extra_bs: write_log(f"Extra basestations: {extra_bs}", "red")
        write_log("Infrastructure migration completed with differences", "red")
    return False

def get_transmission_zones(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/transmission-zones",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting transmission zones: {str(e)}", "red")
        return []

def create_transmission_zone(store, auth_token, zone_name):
    try:
        response = requests.post(
            f"https://{store}.pcm.pricer-plaza.com/api/public/infra/v1/transmission-zones",
            headers={
                "accept": "*/*", 
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json={"name": zone_name}
        )
        response.raise_for_status()
        write_log(f"Created transmission zone '{zone_name}'", "green")
        return True
    except Exception as e:
        write_log(f"Error creating transmission zone '{zone_name}': {str(e)}", "red")
        return False

def migrate_infrastructure(store1, store2, auth_token1, auth_token2, store_data=None):
    source_bs = get_basestations(store1, auth_token1)
    
    if not source_bs or len(source_bs) == 0:
        write_log(f"No basestations found in source store {store1}. MIGRATION ABORTED", "red")
        return False
    
    bs_summary = [{"hardwareId": bs["hardwareId"], "status": bs["detailedStatus"]} for bs in source_bs]
    write_log(f"Get BS Response: {json.dumps(bs_summary)}", "cyan")
    
    bs_not_ready = [bs for bs in source_bs if bs['detailedStatus'] != "IRREADY"]
    if bs_not_ready:
        for bs in bs_not_ready:
            write_log(f"Basestation {bs['hardwareId']} is not ready, status: {bs['detailedStatus']}, MIGRATION ABORTED", "red")
        return False

    target_zones = get_transmission_zones(store2, auth_token2)
    
    for bs in source_bs:
        zone_name = bs.get("transmissionZone")
        if zone_name and zone_name != "Main Store" and zone_name not in target_zones:
            write_log(f"Creating missing transmission zone: {zone_name}", "cyan")
            if create_transmission_zone(store2, auth_token2, zone_name):
                target_zones.append(zone_name)
            else:
                write_log(f"Failed to create transmission zone {zone_name}", "red")

    trx_positions = {}
    from geoloc import check_geoloc_config
    if check_geoloc_config(store1, auth_token1):
        write_log("Geolocation found, collecting transceiver positions", "cyan")
        for bs in source_bs:
            bs_name = bs.get('name')
            trx_positions[bs_name] = {}
            try:
                response = requests.get(
                    f"https://{store1}.pcm.pricer-plaza.com/api/public/infra/v1/basestations/{bs_name}/transceivers",
                    headers={
                        "accept": "*/*",
                        "Authorization": f"Bearer {auth_token1}"
                    }
                )
                response.raise_for_status()
                transceivers = response.json()
                
                write_log(f"GET transceiver locations for BS {bs_name}", "cyan")
                
                for trx in transceivers:
                    if 'address' in trx and 'hwPortNo' in trx['address'] and 'location' in trx and 'position' in trx['location']:
                        port = trx['address']['hwPortNo']
                        if trx['location']['position'].get('x') is not None and trx['location']['position'].get('y') is not None:
                            trx_positions[bs_name][port] = {
                                "height": trx.get('location', {}).get('height', 0),
                                "position": trx.get('location', {}).get('position', {}),
                                "rotation": trx.get('location', {}).get('rotation', 0)
                            }
                            write_log(f"Collected position for BS {bs_name} TRX port {port}", "green")
            except Exception as e:
                write_log(f"Error collecting positions for BS {bs_name}: {str(e)}", "red")
    else:
        write_log("No geolocation found, no need to define Trx position", "yellow")

    bs_secrets = {}
    for bs in source_bs:
        secret = get_bs_secret(bs['hardwareId'])
        if not secret:
            write_log(f"Could not get secret for basestation {bs['hardwareId']}, MIGRATION ABORTED", "red")
            return False
        bs_secrets[bs['hardwareId']] = secret
    
    write_log("All basestation secrets collected successfully", "green")
    
    for bs in source_bs:
        if not add_basestation_to_store(bs['hardwareId'], bs_secrets[bs['hardwareId']], store2, store_data):
            retry_count = 0
            max_retries = 3
            success = False
            
            while retry_count < max_retries and not success:
                retry_count += 1
                write_log(f"Retrying to add basestation {bs['hardwareId']} (attempt {retry_count}/{max_retries})", "yellow")
                time.sleep(10)
                success = add_basestation_to_store(bs['hardwareId'], bs_secrets[bs['hardwareId']], store2, store_data)
                if success:
                    write_log(f"Successfully added basestation {bs['hardwareId']} on retry {retry_count}", "green")
                    break
            
            if not success:
                write_log(f"Failed to pre-add basestation {bs['hardwareId']} after {max_retries} attempts, MIGRATION ABORTED", "red")
                return False
    
    write_log("All basestations pre-added successfully", "green")
    
    source_link_depts = get_link_departments(store1, auth_token1)
    write_log(f"Get LinkDepartment Response: {json.dumps(source_link_depts)}", "cyan")

    target_bs = get_basestations(store2, auth_token2)
    target_link_depts = get_link_departments(store2, auth_token2)
    
    delete_link_departments(store2, auth_token2, target_link_depts)
    for bs in target_bs:
        delete_basestation(store2, auth_token2, bs['name'])

    delete_link_departments(store1, auth_token1, source_link_depts)
    for bs in source_bs:
        delete_basestation(store1, auth_token1, bs['name'])

    if not migrate_basestations(source_bs, store2, auth_token2, bs_secrets):
        write_log("Migration failed", "red")
        return False

    if not recreate_linkdpt(store2, auth_token2, source_link_depts):
        write_log("Failed to recreate link departments", "red")
        return False

    if not restore_backoffice(store2, auth_token2, source_link_depts):
        write_log("Failed to restore backoffice dpt", "red")
        return False

    final_bs = get_basestations(store2, auth_token2)
    final_link_depts = get_link_departments(store2, auth_token2)

    if verify_final_configuration(source_bs, source_link_depts, final_bs, final_link_depts):
        if trx_positions:
            write_log("Applying transceiver positions", "cyan")
            for bs_name, positions in trx_positions.items():
                try:
                    response = requests.get(
                        f"https://{store2}.pcm.pricer-plaza.com/api/public/infra/v1/basestations/{bs_name}/transceivers",
                        headers={
                            "accept": "*/*",
                            "Authorization": f"Bearer {auth_token2}"
                        }
                    )
                    response.raise_for_status()
                    target_transceivers = response.json()
                    
                    for trx in target_transceivers:
                        if 'address' in trx and 'hwPortNo' in trx['address']:
                            port = trx['address']['hwPortNo']
                            if port in positions:
                                try:
                                    position_data = positions[port]
                                    write_log(f"PUT payload for BS {bs_name} TRX {port}: {json.dumps(position_data)}", "cyan")
                                    
                                    response = requests.put(
                                        f"https://{store2}.pcm.pricer-plaza.com/api/public/infra/v1/basestations/{bs_name}/transceivers/{trx['address']['hwPortNo']}",
                                        headers={
                                            "accept": "*/*",
                                            "Authorization": f"Bearer {auth_token2}",
                                            "Content-Type": "application/json"
                                        },
                                        json=position_data
                                    )
                                    response.raise_for_status()
                                    write_log(f"Successfully migrated position for BS {bs_name} TRX {port}", "green")
                                except Exception as e:
                                    write_log(f"Error migrating position for BS {bs_name} TRX {port}: {str(e)}", "red")
                            else:
                                write_log(f"No position data found for BS {bs_name} TRX {port}", "yellow")
                except Exception as e:
                    write_log(f"Error getting transceivers for BS {bs_name}: {str(e)}", "red")
                    
            write_log("Transceiver position migration completed", "green")
        return True
    return False