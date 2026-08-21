import requests
import sys

def test_routing(base_domain="royalsoftwares.co.ke"):
    print(f"Testing Routing for {base_domain}...")
    
    # 1. Test Public API
    api_url = f"https://api.{base_domain}/api/public/tenants/"
    print(f"Testing Public API Endpoint: {api_url}")
    try:
        res = requests.get(api_url, timeout=5)
        print(f"Status: {res.status_code}")
    except Exception as e:
        print(f"Failed: {e}")
        
    # 2. Test Tenant API (assuming a tenant named 'prosper' exists)
    tenant_domain = f"prosper.{base_domain}"
    tenant_url = f"https://api.{base_domain}/api/tenant/info/"
    print(f"\nTesting Tenant API via Host Header for: {tenant_domain}")
    try:
        # In a real setup, the frontend SPA runs on prosper.royalsoftwares.co.ke
        # and makes API requests to api.royalsoftwares.co.ke. 
        # The frontend must pass a custom header or the backend handles wildcard CORS.
        # If the backend handles wildcard CORS, the SPA at prosper... makes a request
        # to api.royalsoftwares.co.ke with `X-Tenant-Schema: prosper` or similar if implemented,
        # OR django-tenants detects the host if the API is directly accessed via prosper...
        
        # Testing if direct subdomain routing works (if API is served via prosper.royalsoftwares.co.ke/api/)
        direct_url = f"https://{tenant_domain}/api/tenant/info/"
        print(f"Trying Direct Subdomain API: {direct_url}")
        res2 = requests.get(direct_url, timeout=5)
        print(f"Status: {res2.status_code}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_routing()
