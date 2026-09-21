#!/usr/bin/env python3
"""
Test the current implementation to verify the fix
"""
import subprocess
import sys

# Test the fix
test_code = '''
import sys
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip")

# Test basic imports
try:
    from app import find_nearby_parks, load_parks_from_cache, geocode_city
    import pandas as pd
    
    print("Testing current implementation...")
    
    # Load parks
    parks_df = load_parks_from_cache()
    print(f"Loaded {len(parks_df)} parks")
    
    # Test with a known city
    coords = geocode_city("Eustace, TX")
    if coords:
        print(f"City coordinates: {coords}")
        
        # Test with time constraint
        result = find_nearby_parks(parks_df, coords, max_hours=2.0)
        print(f"Found {len(result)} parks with 2-hour constraint")
        
        # Test with a reasonable time constraint
        result2 = find_nearby_parks(parks_df, coords, max_hours=8.0)
        print(f"Found {len(result2)} parks with 8-hour constraint")
        
        if len(result2) > 0:
            # Show first few park names
            for i, park in enumerate(result2[:3]):
                print(f"  {i+1}. {park.get('name', 'Unknown')}")
        
        print("✅ Basic functionality working")
    else:
        print("❌ Could not geocode city")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
'''

# Write and run the test
with open('/tmp/test_fix.py', 'w') as f:
    f.write(test_code)

result = subprocess.run([
    '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
    '/tmp/test_fix.py'
], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')

print("Test Output:")
print(result.stdout)
if result.stderr:
    print("Errors:")
    print(result.stderr)
print(f"Return code: {result.returncode}")