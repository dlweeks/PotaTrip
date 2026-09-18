#!/usr/bin/env python3
"""
Test cases for POTA Trip Planner implementation
"""
import sys
import os
import subprocess
import json
import time

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def test_radius_filtering():
    """Test case for radius filtering"""
    print("Testing radius filtering...")
    
    # We'll test by checking if the function works correctly with radius constraints
    from app import find_nearby_parks, load_parks_from_cache, geocode_city
    import pandas as pd
    
    # Load parks
    parks_df = load_parks_from_cache()
    if parks_df is None or parks_df.empty:
        print("Could not load park data")
        return False
    
    # Test with a known city
    city_coords = geocode_city("Dallas, TX")
    if not city_coords:
        print("Could not geocode Dallas, TX")
        return False
    
    # Find parks within 50 miles radius
    parks = find_nearby_parks(parks_df, city_coords, max_distance_miles=50)
    
    print(f"Found {len(parks)} parks within 50 miles")
    
    # Verify all parks are within 50 miles
    from geopy.distance import geodesic
    for park in parks:
        if 'latitude' in park and 'longitude' in park:
            park_coords = (float(park['latitude']), float(park['longitude']))
            distance = geodesic(city_coords, park_coords).miles
            if distance > 50:
                print(f"Error: Park {park.get('name', 'Unknown')} is {distance} miles away")
                return False
    
    print("✓ Radius filtering works correctly")
    return True

def test_hours_filtering():
    """Test case for hours filtering"""
    print("Testing hours filtering...")
    
    # We'll test by checking if the function works correctly with time constraints
    from app import find_nearby_parks, load_parks_from_cache, geocode_city, calculate_driving_time
    import pandas as pd
    
    # Load parks
    parks_df = load_parks_from_cache()
    if parks_df is None or parks_df.empty:
        print("Could not load park data")
        return False
    
    # Test with a known city
    city_coords = geocode_city("Eustace, TX")
    if not city_coords:
        print("Could not geocode Eustace, TX")
        return False
    
    # Find parks within 4 hours (2 hours at park + driving time)
    parks = find_nearby_parks(parks_df, city_coords, max_hours=4)
    
    print(f"Found {len(parks)} parks within 4 hours")
    
    # Verify all parks are within the time limit
    from geopy.distance import geodesic
    for park in parks:
        if 'latitude' in park and 'longitude' in park:
            park_coords = (float(park['latitude']), float(park['longitude']))
            driving_time = calculate_driving_time(city_coords, park_coords)
            total_time = driving_time + 2  # 2 hours at park
            if total_time > 4:
                print(f"Error: Park {park.get('name', 'Unknown')} would take {total_time} hours")
                return False
    
    print("✓ Hours filtering works correctly")
    return True

def test_miles_filtering():
    """Test case for miles filtering"""
    print("Testing miles filtering...")
    
    # We'll test by checking if the function works correctly with distance constraints
    from app import find_nearby_parks, load_parks_from_cache, geocode_city
    import pandas as pd
    
    # Load parks
    parks_df = load_parks_from_cache()
    if parks_df is None or parks_df.empty:
        print("Could not load park data")
        return False
    
    # Test with a known city
    city_coords = geocode_city("Austin, TX")
    if not city_coords:
        print("Could not geocode Austin, TX")
        return False
    
    # Find parks within 200 miles round trip
    parks = find_nearby_parks(parks_df, city_coords, max_miles=200)
    
    print(f"Found {len(parks)} parks within 200 miles")
    
    # Verify all parks are within the distance limit
    from geopy.distance import geodesic
    for park in parks:
        if 'latitude' in park and 'longitude' in park:
            park_coords = (float(park['latitude']), float(park['longitude']))
            driving_time = geodesic(city_coords, park_coords).miles / 40  # 40 mph average
            round_trip_miles = driving_time * 40  # 40 mph * 2 way
            if round_trip_miles > 200:
                print(f"Error: Park {park.get('name', 'Unknown')} has {round_trip_miles} round trip miles")
                return False
    
    print("✓ Miles filtering works correctly")
    return True

def test_cache_management():
    """Test case for cache management"""
    print("Testing cache management...")
    
    from app import is_cache_valid, load_parks_from_cache
    import os
    
    # Check if cache is valid
    is_valid = is_cache_valid()
    print(f"Cache validity: {is_valid}")
    
    # Load parks to ensure cache works
    parks_df = load_parks_from_cache()
    print(f"Loaded {len(parks_df)} parks from cache")
    
    # Check if cache file exists
    cache_file = "/tmp/pota_parks_cache.csv"
    if os.path.exists(cache_file):
        print("✓ Cache file exists")
    else:
        print("✗ Cache file does not exist")
        return False
    
    print("✓ Cache management works correctly")
    return True

def test_google_maps_integration():
    """Test case for Google Maps integration"""
    print("Testing Google Maps integration...")
    
    from app import generate_google_maps_url_with_markers
    import os
    
    # Test with a sample set of parks
    sample_parks = [
        {'latitude': 30.0, 'longitude': -95.0, 'name': 'Test Park 1'},
        {'latitude': 30.5, 'longitude': -95.5, 'name': 'Test Park 2'}
    ]
    
    url = generate_google_maps_url_with_markers("Dallas, TX", sample_parks)
    print(f"Generated URL: {url}")
    
    if url and "google.com/maps" in url:
        print("✓ Google Maps URL generation works correctly")
        return True
    else:
        print("✗ Google Maps URL generation failed")
        return False

def main():
    """Run all tests"""
    print("Running POTA Trip Planner Test Cases...")
    print("=" * 50)
    
    tests = [
        test_radius_filtering,
        test_hours_filtering,
        test_miles_filtering,
        test_cache_management,
        test_google_maps_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with error: {e}")
            failed += 1
        print()
    
    print("=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    main()