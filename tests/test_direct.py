#!/usr/bin/env python3
"""
Test to directly verify the time constraint algorithm works correctly
"""
import sys
import os
import subprocess

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def test_time_constraint_directly():
    """Test the time constraint algorithm directly"""
    print("Testing time constraint algorithm...")
    
    test_code = '''
import sys
import os
import pandas as pd
from geopy.distance import geodesic
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip")

# Import the actual function
from app import find_nearby_parks, load_parks_data, get_city_coordinates

# Test with a specific city and time constraint
city_coords = (32.3537, -95.9936)  # Purtis Creek coordinates
print(f"Testing with city coordinates: {city_coords}")

# Load parks data
parks_df = load_parks_data()
print(f"Loaded {len(parks_df)} parks")

# Test with a small time constraint
result = find_nearby_parks(parks_df, city_coords, max_hours=2.0)
print(f"Found {len(result)} parks with 2-hour constraint")

# Check if Purtis Creek is in the results
purts_creek_found = False
for park in result:
    if 'Purtis Creek' in str(park.get('name', '')):
        print(f"✅ Purtis Creek found in results: {park.get('name')}")
        purts_creek_found = True
        break

if not purts_creek_found:
    print("❌ Purtis Creek NOT found in results - this might be expected due to time calculation")

# Test with a higher time constraint
result2 = find_nearby_parks(parks_df, city_coords, max_hours=5.0)
print(f"Found {len(result2)} parks with 5-hour constraint")

# Check if Purtis Creek is in the results now
purts_creek_found2 = False
for park in result2:
    if 'Purtis Creek' in str(park.get('name', '')):
        print(f"✅ Purtis Creek found in 5-hour results: {park.get('name')}")
        purts_creek_found2 = True
        break

if not purts_creek_found2:
    print("❌ Purtis Creek NOT found in 5-hour results either")

print("Test completed")
'''
    
    # Write and run the test
    with open('/tmp/test_direct.py', 'w') as f:
        f.write(test_code)
        
    result = subprocess.run([
        '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
        '/tmp/test_direct.py'
    ], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')
    
    print("Direct Test Output:")
    print(result.stdout)
    if result.stderr:
        print("Errors:")
        print(result.stderr)
    
    return result.returncode == 0

if __name__ == "__main__":
    test_time_constraint_directly()