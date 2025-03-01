from common import write_log
from endpoint_handler import endpoint_handler
import requests
import time
import json

def get_item_batch(store, auth_token, start=0, limit=1000):
    """Fetch a batch of items from the store"""
    try:
        # Check if this is an onprem store
        is_onprem = not "." in store or ":" in store
        
        if is_onprem:
            url = endpoint_handler.get_full_url("store1", f"/api/public/core/v1/items?projection=M&start={start}&limit={limit}")
            headers = endpoint_handler.get_headers("store1")
            response = requests.get(url, headers=headers, timeout=60)
        else:
            response = requests.get(
                f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/items?projection=M&start={start}&limit={limit}",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token}"
                },
                timeout=60  # Increased timeout for large payloads
            )
        response.raise_for_status()
        items = response.json()
        write_log(f"Retrieved {len(items)} items from {store} (batch starting at {start})", "green")
        return items
    except Exception as e:
        write_log(f"Error fetching items from {store} (batch starting at {start}): {str(e)}", "red")
        return []

def get_linked_item_batch(store, auth_token, start=0, limit=1000):
    """Fetch a batch of linked items from the store"""
    try:
        # Check if this is an onprem store
        is_onprem = not "." in store or ":" in store
        
        if is_onprem:
            url = endpoint_handler.get_full_url("store1", f"/api/private/core/v1/search?queryType=ITEM_BY_ID_OR_NAME_OR_LINKED_BARCODE&projection=M&page={start}&pageSize={limit}&sortDirection=ASC&filter%5Blinked%5D=true")
            headers = endpoint_handler.get_headers("store1")
            response = requests.get(url, headers=headers, timeout=60)
        else:
            response = requests.get(
                f"https://{store}.pcm.pricer-plaza.com/api/private/core/v1/search?queryType=ITEM_BY_ID_OR_NAME_OR_LINKED_BARCODE&projection=M&page={start}&pageSize={limit}&sortDirection=ASC&filter%5Blinked%5D=true",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token}"
                },
                timeout=60  # Increased timeout for large payloads
            )
        response.raise_for_status()
        # The API returns a different structure, we need to extract the content
        result = response.json()
        
        # Check the type of result and handle accordingly
        if isinstance(result, dict):
            items = result.get("content", [])
        elif isinstance(result, list):
            # If result is already a list, use it directly
            items = result
        else:
            items = []
            write_log(f"Unexpected response format from {store} linked items API", "red")
        
        write_log(f"Retrieved {len(items)} linked items from {store} (batch starting at {start})", "green")
        return items
    except Exception as e:
        write_log(f"Error fetching linked items from {store} (batch starting at {start}): {str(e)}", "red")
        return []

def upload_items(store, auth_token, items):
    """Upload a batch of items to the store"""
    if not items:
        write_log("No items to upload", "yellow")
        return True

    try:
        # Check if this is an onprem store
        is_onprem = not "." in store or ":" in store
        
        if is_onprem:
            url = endpoint_handler.get_full_url("store1", "/api/public/core/v1/items")
            headers = endpoint_handler.get_headers("store1")
            response = requests.patch(url, headers=headers, json=items, timeout=60)
        else:
            response = requests.patch(
                f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/items",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json"
                },
                json=items,
                timeout=60  # Increased timeout for large uploads
            )
        response.raise_for_status()
        request_id = response.json().get("requestId")
        write_log(f"Successfully uploaded {len(items)} items to {store}. Request ID: {request_id}", "green")
        return True
    except Exception as e:
        write_log(f"Error uploading items to {store}: {str(e)}", "red")
        return False

def check_request_status(store, auth_token, request_id, max_retries=6, retry_interval=15):
    """Check the status of a request with retries for IN_PROGRESS status"""
    retries = 0
    logged_unknown_properties = set()  # Track properties with unknown property errors
    
    while retries <= max_retries:
        try:
            # Check if this is an onprem store
            is_onprem = not "." in store or ":" in store
            
            if is_onprem:
                url = endpoint_handler.get_full_url("store1", f"/api/public/core/v1/items-result/{request_id}?excludeItemResults=false&excludeItemErrorCount=false")
                headers = endpoint_handler.get_headers("store1")
                response = requests.get(url, headers=headers)
            else:
                response = requests.get(
                    f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/items-result/{request_id}?excludeItemResults=false&excludeItemErrorCount=false",
                    headers={
                        "accept": "application/json",
                        "Authorization": f"Bearer {auth_token}"
                    }
                )
            response.raise_for_status()
            result = response.json()
            status = result.get("status")
            
            if status == "COMPLETED":
                # Safely get itemErrorCount with a default of 0
                error_count = result.get("itemErrorCount", 0)
                
                # Check if there are errors to report
                if error_count and error_count > 0:
                    write_log(f"Upload request {request_id} completed with {error_count} errors", "yellow")
                    
                    # Only process itemResults if it exists and is a list
                    item_results = result.get("itemResults", [])
                    if item_results and isinstance(item_results, list):
                        for item_result in item_results:
                            # Safely check for errors
                            errors = item_result.get("errors", []) if item_result else []
                            if errors and len(errors) > 0:
                                item_id = item_result.get("itemId", "unknown")
                                
                                for error in errors:
                                    if error and isinstance(error, dict):
                                        prop = error.get("property", "unknown")
                                        err_msg = error.get("error", "unknown error")
                                        
                                        # Only log ERROR_UNKNOWN_ITEM_PROPERTY once per property
                                        if err_msg == "ERROR_UNKNOWN_ITEM_PROPERTY":
                                            if prop not in logged_unknown_properties:
                                                logged_unknown_properties.add(prop)
                                                write_log(f"  - Property: {prop}, Error: {err_msg}", "red")
                                        else:
                                            # Log all other errors normally
                                            write_log(f"  - Item {item_id}, Property: {prop}, Error: {err_msg}", "red")
                else:
                    write_log(f"Upload request {request_id} completed successfully", "green")
                return True
            elif status == "IN_PROGRESS":
                if retries < max_retries:
                    write_log(f"Upload request {request_id} is still in progress. Retrying in {retry_interval} seconds... ({retries+1}/{max_retries})", "yellow")
                    time.sleep(retry_interval)
                    retries += 1
                    continue
                else:
                    write_log(f"Upload request {request_id} still in progress after {max_retries} retries", "red")
                    return False
            else:
                write_log(f"Upload request {request_id} status: {status}", "yellow")
                return False
                
        except Exception as e:
            write_log(f"Error checking status for request ID {request_id}: {str(e)}", "red")
            return False
    
    return False  # If we get here, max retries were exceeded

def migrate_items(store1, store2, auth_token1, auth_token2):
    """Migrate all items from store1 to store2"""
    write_log(f"Starting item migration from {store1} to {store2}", "cyan")
    total_items = 0
    batch_size = 1000
    request_ids = []
    
    # Process batches of items
    start_index = 0
    while True:
        # Get a batch of items from source store
        items = get_item_batch(store1, auth_token1, start_index, batch_size)
        
        # Check if we've reached the end of the items
        if not items:
            break
            
        # Check if this is an onprem store
        is_onprem = not "." in store2 or ":" in store2
        
        if is_onprem:
            url = endpoint_handler.get_full_url("store2", "/api/public/core/v1/items")
            headers = endpoint_handler.get_headers("store2")
            response = requests.patch(url, headers=headers, json=items, timeout=120)
        else:
            response = requests.patch(
                f"https://{store2}.pcm.pricer-plaza.com/api/public/core/v1/items",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token2}",
                    "Content-Type": "application/json"
                },
                json=items,
                timeout=120
            )
        if response.status_code in [200, 201, 202]:
            request_id = response.json().get("requestId")
            request_ids.append(request_id)
            write_log(f"Successfully uploaded {len(items)} items to {store2}. Request ID: {request_id}", "green")
        else:
            write_log(f"Failed to upload batch starting at index {start_index}. Status: {response.status_code}", "red")
            return False
            
        total_items += len(items)
        
        # If we got less than the batch size, we've reached the end
        if len(items) < batch_size:
            break
            
        # Move to next batch
        start_index += batch_size
        
        # Short pause to avoid overloading the API
        time.sleep(1)
    
    # Add an initial wait before checking request statuses
    if request_ids:
        write_log(f"Waiting 15 seconds before checking request statuses...", "cyan")
        time.sleep(15)
    
    # Now check all request IDs for status and errors
    success_count = 0
    for request_id in request_ids:
        write_log(f"Checking upload status for request ID: {request_id}", "cyan")
        if check_request_status(store2, auth_token2, request_id, max_retries=6, retry_interval=10):
            success_count += 1
    
    write_log(f"Item migration complete! Migrated {total_items} items from {store1} to {store2}", "green")
    write_log(f"Upload status summary: {success_count}/{len(request_ids)} batches completed successfully", "green" if success_count == len(request_ids) else "yellow")
    return success_count == len(request_ids)

def migrate_linked_items(store1, store2, auth_token1, auth_token2):
    """Migrate linked items from store1 to store2"""
    write_log(f"Starting linked item migration from {store1} to {store2}", "cyan")
    total_items = 0
    batch_size = 1000
    request_ids = []
    
    # Process batches of items
    start_index = 0
    while True:
        # Get a batch of linked items from source store
        items = get_linked_item_batch(store1, auth_token1, start_index, batch_size)
        
        # Check if we've reached the end of the items
        if not items:
            break
            
        # Check if this is an onprem store
        is_onprem = not "." in store2 or ":" in store2
        
        if is_onprem:
            url = endpoint_handler.get_full_url("store2", "/api/public/core/v1/items")
            headers = endpoint_handler.get_headers("store2")
            response = requests.patch(url, headers=headers, json=items, timeout=120)
        else:
            response = requests.patch(
                f"https://{store2}.pcm.pricer-plaza.com/api/public/core/v1/items",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token2}",
                    "Content-Type": "application/json"
                },
                json=items,
                timeout=120
            )
        if response.status_code in [200, 201, 202]:
            request_id = response.json().get("requestId")
            request_ids.append(request_id)
            write_log(f"Successfully uploaded {len(items)} linked items to {store2}. Request ID: {request_id}", "green")
        else:
            write_log(f"Failed to upload batch starting at index {start_index}. Status: {response.status_code}", "red")
            return False
            
        total_items += len(items)
        
        # If we got less than the batch size, we've reached the end
        if len(items) < batch_size:
            break
            
        # Move to next batch
        start_index += batch_size
        
        # Short pause to avoid overloading the API
        time.sleep(1)
    
    # Add an initial wait before checking request statuses
    if request_ids:
        write_log(f"Waiting 15 seconds before checking request statuses...", "cyan")
        time.sleep(15)
    
    # Now check all request IDs for status and errors
    success_count = 0
    for request_id in request_ids:
        write_log(f"Checking upload status for request ID: {request_id}", "cyan")
        if check_request_status(store2, auth_token2, request_id, max_retries=6, retry_interval=10):
            success_count += 1
    
    write_log(f"Linked item migration complete! Migrated {total_items} linked items from {store1} to {store2}", "green")
    write_log(f"Upload status summary: {success_count}/{len(request_ids)} batches completed successfully", "green" if success_count == len(request_ids) else "yellow")
    return success_count == len(request_ids)