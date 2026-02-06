#!/usr/bin/env python3
"""Enable a sector via API."""
import requests

response = requests.post(
    "http://localhost:8000/universe/sectors/core_index/enable",
    json={"enabled": True}
)
print(f"Status: {response.status_code}")
print(response.json())
