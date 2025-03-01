import requests
from common import write_log

class EndpointHandler:
    def __init__(self):
        self.endpoints = {}
        
    def register_endpoint(self, store_id, base_url, is_https=True, auth_type="bearer", auth_value=None):
        """Register a store endpoint with its base URL and auth details"""
        self.endpoints[store_id] = {
            "base_url": base_url,
            "is_https": is_https,
            "auth_type": auth_type,  # "bearer" or "basic"
            "auth_value": auth_value
        }
        
    def get_base_url(self, store_id):
        """Get the base URL for a store"""
        if store_id in self.endpoints:
            return self.endpoints[store_id]["base_url"]
        return None
        
    def get_headers(self, store_id):
        """Get authentication headers for a store"""
        if store_id not in self.endpoints:
            return {}
            
        endpoint = self.endpoints[store_id]
        if endpoint["auth_type"] == "bearer":
            return {"Authorization": f"Bearer {endpoint['auth_value']}"}
        elif endpoint["auth_type"] == "basic":
            return {"Authorization": f"Basic {endpoint['auth_value']}"}
        return {}
        
    def get_full_url(self, store_id, api_path):
        """Get the full URL for an API endpoint"""
        if store_id not in self.endpoints:
            return None
            
        endpoint = self.endpoints[store_id]
        protocol = "https" if endpoint["is_https"] else "http"
        return f"{protocol}://{endpoint['base_url']}{api_path}"
        
    def check_api_availability(self, store_id, api_path):
        """Check if an API endpoint is available"""
        full_url = self.get_full_url(store_id, api_path)
        if not full_url:
            return False
            
        try:
            headers = self.get_headers(store_id)
            response = requests.head(full_url, headers=headers, timeout=3)
            return response.status_code < 400  # Any success or redirect status
        except:
            try:
                # Try GET if HEAD is not supported
                response = requests.get(full_url, headers=headers, timeout=3)
                return response.status_code < 400
            except:
                return False

# Global instance
endpoint_handler = EndpointHandler()
