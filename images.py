import requests
import os
from common import write_log
from urllib.parse import quote

def get_folders_and_files(store, auth_token, folder_path="", page_index=0, page_size=100):
    normalized_path = folder_path.replace('\\', '/')
    url = f"https://{store}.pcm.pricer-plaza.com/api/public/file/v1/image-folder"
    params = {
        "folderPath": normalized_path,
        "pageIndex": page_index, 
        "pageSize": page_size
    }
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        write_log(f"Error fetching folders and files: {str(e)}", "red")
        return []
    
    data = response.json()
    # Filter out pricer_logo.png from the files list
    files = [os.path.join(folder_path, f).replace('\\', '/') for f in data["files"] if f.lower() != "pricer_logo.png"]
    
    for folder in data["folders"]:
        # Use os.path.join for the subfolder path instead of combining with current folder_path
        subfolder_path = folder if not folder_path else f"{folder_path}/{folder}"
        files.extend(get_folders_and_files(store, auth_token, subfolder_path))
        
    if data["totalSize"] > (page_index + 1) * page_size:
        files.extend(get_folders_and_files(store, auth_token, folder_path, page_index + 1))
        
    return files

def download_file(store, auth_token, file_path):
    normalized_path = file_path.replace('\\', '/')
    url = f"https://{store}.pcm.pricer-plaza.com/api/public/file/v1/image"
    params = {"filePath": normalized_path}  # requests will handle URL encoding
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.content

def upload_file(store, auth_token, file_path, file_content):
    # Get destination folder path, defaulting to root '/'
    folder_path = '/' + os.path.dirname(file_path).lstrip('/')
    if folder_path == '/.': folder_path = '/'
    
    url = f"https://{store}.pcm.pricer-plaza.com/api/public/file/v1/image"
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Get file extension for content type
    ext = os.path.splitext(file_path)[1].lower()
    content_type = {
        '.png': 'image/png',
        '.bmp': 'image/bmp',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg'
    }.get(ext, 'application/octet-stream')
    
    files = {
        'image': (
            os.path.basename(file_path),
            file_content,
            content_type
        )
    }
    
    params = {'filePath': folder_path}
    response = requests.post(url, headers=headers, files=files, params=params)
    response.raise_for_status()
    
def migrate_images(store1, store2, auth_token1, auth_token2):
    write_log(f"Fetching files from {store1}", "cyan")
    files = get_folders_and_files(store1, auth_token1)
    
    for file in files:
        write_log(f"Downloading {file} from {store1}", "cyan")
        file_content = download_file(store1, auth_token1, file)
        
        write_log(f"Uploading {file} to {store2}", "cyan")
        try:
            upload_file(store2, auth_token2, file, file_content)
            write_log(f"Successfully uploaded {file} to {store2}", "green") 
        except Exception as e:
            write_log(f"Failed to upload {file} to {store2}: {str(e)}", "red")
            
    write_log("Image migration complete", "green")