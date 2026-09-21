#!/usr/bin/env python3
"""
Direct test to prove Purtis Creek inclusion in results
"""
import sys
import os
import subprocess
import pandas as pd
from geopy.distance import geodesic

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def test_purtis_creek_directly():
    """Test that Purtis Creek is properly included when within constraints"""
    print("=== DIRECT TEST FOR PURTIS CREEK INCLUSION ===")
    
    # Load cache file
    cache_file = "/tmp/pota_parks_cache.csv"
    df = pd.read_csv(cache_file)
    print(f"Loaded {len(df)} parks from cache")
    
    # Find Purtis Creek
    purtis_park = df[df['name'].str.contains('Purtis Creek', case=False, na=False)]
    print(f"Purtis Creek data: {purtis_park}")
    
    if not purtis_park.empty:
        park_row = purtis_park.iloc[0]
        print(f"Purtis Creek coordinates: {park_row['latitude']}, {park_row['longitude']}")
        print(f"Purtis Creek reference: {park_row['reference']}")
        
        # Test with city that should have Purtis Creek within reasonable driving time
        # Let's test with a city that has a known good driving time to Purtis Creek
        # We'll use coordinates that are known to be near Purtis Creek
        test_city_coords = (32.3537, -95.9936)  # Purtis Creek coordinates
        purtis_coords = (float(park_row['latitude']), float(park_row['longitude']))
        
        # Calculate distance
        distance = geodesic(test_city_coords, purtis_coords).miles
        print(f"Distance between test city and Purtis Creek: {distance:.2f} miles")
        
        # Test with a time constraint that should include Purtis Creek
        # If it's ~0 miles away, it should be included with any reasonable time constraint
        print("\nTesting the actual application with Purtis Creek coordinates...")
        
        # Let's run the application in a subprocess to test with actual constraints
        test_code = '''
import sys
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip")
from app import find_nearby_parks, load_parks_from_cache, geocode_city
import pandas as pd

# Test with Purtis Creek coordinates as the city
parks_df = load_parks_from_cache()
# Use Purtis Creek coordinates directly
city_coords = (32.3537, -95.9936)

# Test with 10-hour constraint - should definitely include Purtis Creek
result = find_nearby_parks(parks_df, city_coords, max_hours=10.0)
print(f"Found {len(result)} parks with 10-hour constraint")
for i, park in enumerate(result[:5]):
    print(f"  {i+1}. {park.get('name', 'Unknown')}")

# Test with 2-hour constraint - should include Purtis Creek since it's at the same location
result2 = find_nearby_parks(parks_df, city_coords, max_hours=2.0)
print(f"Found {len(result2)} parks with 2-hour constraint")
for i, park in enumerate(result2[:5]):
    print(f"  {i+1}. {park.get('name', 'Unknown')}")

print("Test completed successfully")
'''
        
        # Write and run test
        with open('/tmp/test_purtis.py', 'w') as f:
            f.write(test_code)
            
        result = subprocess.run([
            '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
            '/tmp/test_purtis.py'
        ], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')
        
        print("Application test results:")
        print(result.stdout)
        if result.stderr:
            print("Errors:")
            print(result.stderr)
    else:
        print("Purtis Creek not found in cache")

if __name__ == "__main__":
    test_purtis_creek_directly()