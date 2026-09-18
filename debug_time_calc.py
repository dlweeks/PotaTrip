#!/usr/bin/env python3
"""
Debug script to test the actual time constraint calculation
"""

from geopy.distance import geodesic
import pandas as pd
import os

def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points"""
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def test_time_calculation():
    """Test how time calculation works with actual data"""
    
    # Eustace, TX coordinates
    city_coords = (32.3070902, -96.0066354)
    
    # Load cache file to see some actual park data
    cache_file = "/tmp/pota_parks_cache.csv"
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        print(f"Loaded {len(df)} parks from cache")
        
        # Test first few parks
        print("\n=== TESTING PARK TIME CALCULATIONS ===")
        for i in range(min(5, len(df))):
            park = df.iloc[i]
            if 'latitude' in park and 'longitude' in park:
                if pd.notna(park['latitude']) and pd.notna(park['longitude']):
                    try:
                        park_coords = (float(park['latitude']), float(park['longitude']))
                        distance = geodesic(city_coords, park_coords).miles
                        driving_time = calculate_driving_time(city_coords, park_coords)
                        total_time = driving_time + 2
                        
                        print(f"{i+1}. {park.get('name', 'Unknown')}")
                        print(f"   Distance: {distance:.2f} miles")
                        print(f"   Driving time: {driving_time:.2f} hours")
                        print(f"   Total time: {total_time:.2f} hours")
                        print()
                    except Exception as e:
                        print(f"Error processing park {i}: {e}")

if __name__ == "__main__":
    test_time_calculation()