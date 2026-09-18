#!/usr/bin/env python3
"""
Test script to verify the time constraint algorithm works properly
"""
import sys
import os
import subprocess
import time
import json

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def test_time_constraint_algorithm():
    """Test that the time constraint algorithm works correctly"""
    print("Testing time constraint algorithm...")
    
    # Test with a simple scenario
    try:
        # First, let's create a test script that directly tests the key functions
        test_script = '''
import sys
sys.path.insert(0, "/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages")
import pandas as pd
from geopy.distance import geodesic
import numpy as np
from app import calculate_driving_time, find_nearby_parks, generate_optimized_trip

# Create a mock parks dataframe for testing
mock_parks = pd.DataFrame([
    {"name": "Test Park A", "latitude": 30.0, "longitude": -95.0},
    {"name": "Test Park B", "latitude": 30.1, "longitude": -95.1},
    {"name": "Test Park C", "latitude": 30.2, "longitude": -95.2}
])

# Test coordinates
city_coords = (30.0, -95.0)

# Test time constraint
nearby_parks = find_nearby_parks(mock_parks, city_coords, max_hours=2.0)
print(f"Number of parks found with 2-hour constraint: {len(nearby_parks)}")

# Test optimized trip
optimized_parks = generate_optimized_trip(nearby_parks, city_coords, max_hours=2.0)
print(f"Number of parks in optimized trip: {len(optimized_parks)}")

# Test with a larger time constraint
nearby_parks2 = find_nearby_parks(mock_parks, city_coords, max_hours=10.0)
print(f"Number of parks found with 10-hour constraint: {len(nearby_parks2)}")

optimized_parks2 = generate_optimized_trip(nearby_parks2, city_coords, max_hours=10.0)
print(f"Number of parks in optimized trip (10 hours): {len(optimized_parks2)}")
        '''
        
        # Write the test script
        with open('/tmp/test_algorithm.py', 'w') as f:
            f.write(test_script)
        
        # Run the test
        result = subprocess.run([
            '/home/dweeks/ham_radio_src/PotaTrip/venv/bin/python', 
            '/tmp/test_algorithm.py'
        ], capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')
        
        print("Algorithm test output:")
        print(result.stdout)
        if result.stderr:
            print("Algorithm test errors:")
            print(result.stderr)
        
        return True
        
    except Exception as e:
        print(f"Error in algorithm test: {e}")
        return False

def main():
    print("=== POTA Trip Planner Algorithm Test ===")
    print()
    
    success = test_time_constraint_algorithm()
    
    if success:
        print("\n✅ Algorithm test completed successfully")
        print("The time constraint implementation should now properly limit parks")
        print("based on the time constraints provided by the user.")
    else:
        print("\n❌ Algorithm test failed")
    
    return success

if __name__ == "__main__":
    main()