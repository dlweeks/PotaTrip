#!/usr/bin/env python3
"""
Direct test to verify Purtis Creek is now included in results
"""
import sys
import subprocess

test_code = '''
import sys
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip")

# Test the fixed implementation
from app import find_nearby_parks, load_parks_from_cache, geocode_city
import pandas as pd

print("=== TESTING FIXED IMPLEMENTATION ===")

# Load parks data
parks_df = load_parks_from_cache()
print(f"Loaded {len(parks_df)} parks")

# Test with a city that should have POTA parks
city_coords = geocode_city("Dallas, TX")
if city_coords:
    print(f"Using Dallas coordinates: {city_coords}")
    
    # Test with a reasonable constraint
    result = find_nearby_parks(parks_df, city_coords, max_hours=8.0)
    print(f"Found {len(result)} parks with 8-hour constraint")
    
    # Check if Purtis Creek is included (it should be since it's a valid POTA park)
    purtis_found = False
    for park in result:
        if "Purtis Creek" in str(park.get("name", "")):
            print("✅ Purtis Creek FOUND in results!")
            purtis_found = True
            break
    
    if not purtis_found:
        print("⚠️  Purtis Creek NOT found in results")
        # Show first few park names to see what's being returned
        print("First 10 park names:")
        for i, park in enumerate(result[:10]):
            print(f"  {i+1}. {park.get('name', 'Unknown')}")
    
    print("✅ Test completed")
else:
    print("❌ Could not geocode city")

'''

with open('/tmp/test_fixed.py', 'w') as f:
    f.write(test_code)

result = subprocess.run([
    '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
    '/tmp/test_fixed.py'
], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')

print("Test Output:")
print(result.stdout)
if result.stderr:
    print("Errors:")
    print(result.stderr)
print(f"Return code: {result.returncode}")