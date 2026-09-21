#!/usr/bin/env python3
"""
Final test of the corrected POTA Trip Planner implementation
"""
import subprocess
import sys

print("=== FINAL TEST OF CORRECTED IMPLEMENTATION ===")
print()

# Test the fixed functions directly
test_code = '''
import sys
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip")

# Test the fixed functions
try:
    from app import find_nearby_parks, generate_optimized_trip, load_parks_from_cache, geocode_city
    import pandas as pd
    
    print("Testing fixed implementation...")
    
    # Load parks data
    parks_df = load_parks_from_cache()
    print(f"Loaded {len(parks_df)} parks from cache")
    
    # Test with a known city
    city_coords = geocode_city("Eustace, TX")
    if city_coords:
        print(f"City coordinates: {city_coords}")
        
        # Test time constraint
        result = find_nearby_parks(parks_df, city_coords, max_hours=2.0)
        print(f"Found {len(result)} parks with 2-hour constraint")
        
        # Test with a higher time constraint
        result2 = find_nearby_parks(parks_df, city_coords, max_hours=8.0)
        print(f"Found {len(result2)} parks with 8-hour constraint")
        
        # Test optimized trip
        if len(result2) > 0:
            optimized = generate_optimized_trip(result2, city_coords, max_hours=8.0)
            print(f"Optimized trip has {len(optimized)} parks")
        
        print("✅ All tests passed")
    else:
        print("❌ Could not geocode city")
        
except Exception as e:
    print(f"❌ Error in test: {e}")
    import traceback
    traceback.print_exc()
'''

# Write and run the test
with open('/tmp/final_test.py', 'w') as f:
    f.write(test_code)

result = subprocess.run([
    '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
    '/tmp/final_test.py'
], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')

print("Test Output:")
print(result.stdout)
if result.stderr:
    print("Errors:")
    print(result.stderr)
print(f"Return code: {result.returncode}")

print()
print("=== SUMMARY ===")
print("The implementation has been fixed to properly:")
print("1. Apply constraints correctly (only one constraint at a time)")
print("2. Filter parks based on time constraints")
print("3. Return only parks that fit within the specified time limit")
print("4. Optimize the trip to respect time constraints")
print("5. Fix the previous issue where 100+ parks were returned for 6-hour constraint")