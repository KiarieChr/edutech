import urllib.request
import urllib.error

try:
    req = urllib.request.Request('http://127.0.0.1:8000/en/workforce/api/leave-applications/analytics/')
    req.add_header('Accept', 'application/json')
    response = urllib.request.urlopen(req)
    print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}")
    print(e.read().decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
