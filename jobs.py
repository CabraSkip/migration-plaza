from common import write_log
import requests

def get_jobs(store, auth_token):
    try:
        response = requests.get(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/jobs",
            headers={
                "accept": "*/*",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        write_log(f"Error getting jobs from {store}: {str(e)}", "red")
        return None

def create_job(store, auth_token, job_data):
    job_id = job_data["id"]
    try:
        response = requests.put(
            f"https://{store}.pcm.pricer-plaza.com/api/public/config/v1/jobs/{job_id}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=job_data
        )
        response.raise_for_status()
        write_log(f"Successfully migrated job {job_id} ({job_data['name']})", "green")
        return True
    except Exception as e:
        write_log(f"Error creating job {job_id}: {str(e)}", "red")
        return False

def migrate_jobs(store1, store2, auth_token1, auth_token2):
    write_log(f"Getting jobs from {store1}", "cyan")
    jobs = get_jobs(store1, auth_token1)
    
    if not jobs:
        write_log("No jobs found in source store", "yellow")
        return False

    success_count = 0
    for job in jobs:
        if create_job(store2, auth_token2, job):
            success_count += 1

    write_log(f"Jobs migration complete. {success_count}/{len(jobs)} jobs migrated", "green")
    return True