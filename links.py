import requests
import json
import time
from common import write_log
from tqdm import tqdm
from collections import defaultdict
from endpoint_handler import endpoint_handler

def get_links(store, auth_token, batch_size=20000):
    """
    Get all links from the specified store using the labels API
    with support for pagination to handle large datasets
    """
    write_log(f"Fetching links from {store}...", "cyan")
    all_links = []
    start = 0
    
    try:
        # Check if this is an onprem store
        is_onprem = not "." in store or ":" in store
        
        while True:
            if is_onprem:
                url = endpoint_handler.get_full_url("store1", f"/api/public/core/v1/labels?projection=M&start={start}&limit={batch_size}&serializeDatesToIso8601=true")
                headers = endpoint_handler.get_headers("store1")
                response = requests.get(url, headers=headers)
            else:
                url = f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/labels?projection=M&start={start}&limit={batch_size}&serializeDatesToIso8601=true"
                headers = {
                    "accept": "application/json",
                    "Authorization": f"Bearer {auth_token}"
                }
                response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                write_log(f"Failed to get links: {response.status_code} - {response.text}", "red")
                return None
            
            batch_data = response.json()
            batch_count = len(batch_data)
            all_links.extend(batch_data)
            
            write_log(f"Fetched batch of {batch_count} links (total so far: {len(all_links)})", "cyan")
            
            # If we got fewer results than the batch size, we've reached the end
            if batch_count < batch_size:
                break
                
            start += batch_size
            # Small delay to prevent rate limiting
            time.sleep(0.5)
        
        write_log(f"Successfully fetched {len(all_links)} links from {store}", "green")
        return all_links
    
    except Exception as e:
        write_log(f"Error getting links: {str(e)}", "red")
        return None

def check_request_status(store, auth_token, request_id, max_attempts=10, wait_time=60, initial_wait=15):
    """
    Check the status of a request using the labels-result API
    Returns a tuple (success, error_summary)
    Treats IN_PROGRESS as COMPLETED and ignores PENDING items in results.
    """
    # Check if this is an onprem store
    is_onprem = not "." in store or ":" in store

    if is_onprem:
        url = endpoint_handler.get_full_url("store1", f"/api/public/core/v1/labels-result/{request_id}")
        headers = endpoint_handler.get_headers("store1")
    else:
        url = f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/labels-result/{request_id}"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
    
    # Store detailed error information
    error_summary = defaultdict(list)
    
    # Wait initially before checking status
    write_log(f"Waiting {initial_wait} seconds before first status check...", "cyan")
    time.sleep(initial_wait)
    
    for attempt in range(max_attempts):
        try:
            write_log(f"Checking request status (attempt {attempt+1}/{max_attempts}), request ID: {request_id}", "cyan")
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                
                # Extract overall status
                status = result.get("status")
                
                # Only log if status is different from PENDING
                if status != "PENDING":
                    write_log(f"Request status: {status}", "cyan")
                
                # Check if processing is complete or in progress (treat IN_PROGRESS as COMPLETED)
                if status in ["COMPLETED", "IN_PROGRESS"]:
                    # Process item results for detailed reporting
                    if "results" in result:
                        error_count = 0
                        success_count = 0
                        pending_count = 0
                        
                        # Group errors by type
                        for item in result["results"]:
                            item_status = item.get("status", "")
                            
                            if item_status in ["SUCCESS", "SUCCESS_NEW_ITEM"]:
                                success_count += 1
                            elif item_status == "PENDING":
                                # Ignore items with PENDING status
                                pending_count += 1
                            else:
                                error_count += 1
                                # Store error details with barcode and itemId if available
                                error_info = {}
                                if "barcode" in item:
                                    error_info["barcode"] = item["barcode"]
                                if "itemId" in item:
                                    error_info["itemId"] = item["itemId"]
                                
                                error_summary[item_status].append(error_info)
                        
                        # Generate error summary
                        if error_count > 0:
                            write_log(f"Request processed with {error_count} errors, {success_count} successes, {pending_count} still pending", "yellow")
                            return (False, error_summary)
                        else:
                            write_log(f"Request {request_id} processed successfully with {success_count} successes, {pending_count} still pending", "green")
                            return (True, error_summary)
                    else:
                        write_log(f"Request {request_id} processed but no item results found", "yellow")
                        return (True, error_summary)
                    
                elif status == "FAILED":
                    write_log(f"Request {request_id} failed: {result.get('reason', 'Unknown reason')}", "red")
                    return (False, error_summary)
            else:
                write_log(f"Failed to check request status: {response.status_code} - {response.text}", "red")
            
            # Wait before trying again
            time.sleep(wait_time)
            
        except Exception as e:
            write_log(f"Error checking request status: {str(e)}", "red")
            time.sleep(wait_time)
    
    write_log(f"Request status check timed out after {max_attempts} attempts", "red")
    return (False, error_summary)

def upload_links(store, auth_token, links_data, batch_size=20000):
    """
    Upload links to the specified store using the labels API
    with batching for more reliable uploads.
    First uploads all batches, then checks status of all requests.
    """
    write_log(f"Uploading {len(links_data)} links to {store}...", "cyan")
    
    try:
        # Check if this is an onprem store
        is_onprem = not "." in store or ":" in store

        if is_onprem:
            url = endpoint_handler.get_full_url("store1", "/api/public/core/v1/labels")
            headers = endpoint_handler.get_headers("store1")
        else:
            url = f"https://{store}.pcm.pricer-plaza.com/api/public/core/v1/labels"
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}"
            }
        
        # Process in batches
        total_links = len(links_data)
        successful_uploads = 0
        failed_uploads = 0
        all_errors = defaultdict(list)
        pending_requests = []
        
        # Step 1: Upload all batches first
        write_log(f"Step 1: Uploading {len(links_data)//batch_size + (1 if len(links_data) % batch_size else 0)} batches", "cyan")
        for i in tqdm(range(0, total_links, batch_size), desc="Uploading batches"):
            batch = links_data[i:i+batch_size]
            batch_number = i//batch_size + 1
            
            # Log batch info
            write_log(f"Uploading batch {batch_number} ({len(batch)} links)", "cyan")
            
            try:
                response = requests.patch(url, headers=headers, json=batch, timeout=60)
                
                if response.status_code == 200:
                    successful_uploads += len(batch)
                    write_log(f"Batch {batch_number} upload successful with status 200", "green")
                elif response.status_code == 202:
                    # Request accepted for processing
                    response_data = response.json()
                    request_id = response_data.get("requestId")
                    if request_id:
                        write_log(f"Batch {batch_number} accepted for processing with request ID: {request_id}", "yellow")
                        pending_requests.append({
                            "request_id": request_id,
                            "batch_size": len(batch),
                            "batch_number": batch_number
                        })
                    else:
                        write_log(f"Batch {batch_number}: Received status 202 but no requestId in response", "red")
                        failed_uploads += len(batch)
                else:
                    write_log(f"Batch {batch_number} upload failed: {response.status_code} - {response.text}", "red")
                    failed_uploads += len(batch)
            except Exception as batch_error:
                write_log(f"Error uploading batch {batch_number}: {str(batch_error)}", "red")
                failed_uploads += len(batch)
            
            # Short pause between batches
            time.sleep(1)
        
        # Step 2: Check status of all pending requests
        if pending_requests:
            write_log(f"\nStep 2: Checking status of {len(pending_requests)} pending requests", "cyan")
            for request_info in tqdm(pending_requests, desc="Checking request statuses"):
                request_id = request_info["request_id"]
                batch_number = request_info["batch_number"]
                batch_size = request_info["batch_size"]
                
                write_log(f"Checking status of batch {batch_number} (request ID: {request_id})", "cyan")
                request_success, error_summary = check_request_status(store, auth_token, request_id)
                
                if request_success:
                    successful_uploads += batch_size
                    write_log(f"Batch {batch_number} processing completed successfully", "green")
                else:
                    # Count failed items based on error summary
                    error_count = sum(len(items) for items in error_summary.values())
                    failed_uploads += error_count
                    successful_uploads += (batch_size - error_count)
                    
                    # Merge the error summaries across batches
                    for error_type, items in error_summary.items():
                        all_errors[error_type].extend(items)
                        
                    write_log(f"Batch {batch_number} processing completed with {error_count} errors", "yellow")
        
        # Final summary of all errors across all batches
        if all_errors:
            write_log("\n--- Error Summary ---", "yellow")
            for error_type, items in all_errors.items():
                if error_type == "UNKNOWN":
                    barcodes = [item.get("barcode", "unknown") for item in items]
                    write_log(f"Error {error_type}: {len(items)} ; plbarcodes: {', '.join(barcodes)}", "red")
                elif error_type == "ERROR_NO_LINK_DEPARTMENTS":
                    write_log(f"Error {error_type}: {len(items)}", "red")
                else:
                    item_ids = [item.get("itemId", "unknown") for item in items if "itemId" in item]
                    if item_ids:
                        write_log(f"Error {error_type}: {len(items)} ; ItemIds: {', '.join(item_ids)}", "red")
                    else:
                        write_log(f"Error {error_type}: {len(items)}", "red")
        
        write_log(f"Upload summary: {successful_uploads} successful, {failed_uploads} failed Out of {total_links} total links", "cyan")
        return failed_uploads == 0, successful_uploads, failed_uploads
    
    except Exception as e:
        write_log(f"Error uploading links: {str(e)}", "red")
        return False, 0, total_links

def clean_link_data(link):
    """
    Clean and prepare link data for migration by removing unwanted properties
    """
    # Create a copy to avoid modifying the original
    clean_link = link.copy()
    
    # Properties to be removed
    properties_to_remove = ["batteryState", "plState", "lastSeen", "lastModified", "version"]
    
    for prop in properties_to_remove:
        if prop in clean_link:
            del clean_link[prop]
    
    return clean_link

def migrate_links(store1, store2, auth_token1, auth_token2):
    """
    Migrate links from store1 to store2
    """
    write_log(f"\n--- Starting links migration from {store1} to {store2} ---", "yellow")
    
    # Get links from source store
    links_data = get_links(store1, auth_token1)
    
    if not links_data:
        write_log("No links found or error fetching links", "red")
        return False
    
    # Count the links
    total_links = len(links_data)
    write_log(f"Found {total_links} links to migrate", "green")
    
    if total_links == 0:
        write_log("No links to migrate", "yellow")
        return False
    
    # Clean links data - remove unwanted properties
    write_log("Cleaning link data for migration...", "cyan")
    cleaned_links = []
    for link in tqdm(links_data, desc="Processing links"):
        cleaned_links.append(clean_link_data(link))
    
    # Upload links to target store
    write_log(f"Uploading {len(cleaned_links)} links to {store2}...", "cyan")
    upload_result, successful_uploads, failed_uploads = upload_links(store2, auth_token2, cleaned_links)
    
    if upload_result:
        write_log(f"Successfully migrated: {total_links}", "green")
        return True
    else:
        # Check if we had at least one successful upload but not complete success
        if successful_uploads > 0 and failed_uploads > 0:
            write_log("\n--- Links Migration completed with errors ---", "yellow")
        else:
            write_log("\n--- Links Migration Failed ---", "red")
        return False
