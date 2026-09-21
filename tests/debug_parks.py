#!/usr/bin/env python3
"""
Debug version to show exactly which parks are being returned
"""

import pandas as pd
import sys
import os
from geopy.distance import geodesic

# Mock the same logic as in app.py
def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points"""
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def find_nearby_parks_debug(parks_df, city_coords, max_hours=None):
    """Debug version that shows exactly what's being returned"""
    print(f"DEBUG: Searching for parks near {city_coords} with {max_hours} hour constraint")
    print(f"DEBUG: Total parks in dataset: {len(parks_df)}")
    
    nearby_parks = []
    
    # Check if we have data
    if parks_df.empty:
        print("DEBUG: No parks data")
        return []
    
    # Filter out non-POTA parks and check distances
    count = 0
    for index, park in parks_df.iterrows():
        count += 1
        if count > 20:  # Limit for debug
            break
            
        # Check if we have the coordinates
        if 'latitude' in park and 'longitude' in park:
            # Handle potential NaN values
            if pd.isna(park['latitude']) or pd.isna(park['longitude']):
                continue
                
            # Ensure latitude is within valid range
            if -90 <= float(park['latitude']) <= 90:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(city_coords, park_coords).miles
                
                # Apply constraints
                if max_hours is not None:
                    # Calculate time to park and back
                    driving_time = calculate_driving_time(city_coords, park_coords)
                    # Time constraint: 2 hours at park + driving time
                    total_time = driving_time + 2  # 2 hours at park + driving time
                    
                    # If this park can be visited within the time limit, add it
                    if total_time <= max_hours:
                        nearby_parks.append({
                            'park': park,
                            'distance': distance,
                            'driving_time': driving_time,
                            'total_time': total_time
                        })
                        print(f"DEBUG: Added {park.get('name', 'Unknown')} - Driving: {driving_time:.2f}h, Total: {total_time:.2f}h")
                else:
                    print(f"DEBUG: Skipping due to no constraint - {park.get('name', 'Unknown')}")
    
    print(f"DEBUG: Found {len(nearby_parks)} parks within {max_hours} hours")
    return nearby_parks

def main():
    print("=== DEBUG PARK SELECTION ===")
    
    # Load parks (simplified for this debug)
    cache_file = "/tmp/pota_parks_cache.csv"
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        print(f"Loaded {len(df)} parks from cache")
        
        # Test with Eustace, TX coordinates
        city_coords = (32.3070902, -96.0066354)
        max_hours = 6.0
        
        parks = find_nearby_parks_debug(df, city_coords, max_hours)
        
        print(f"\n=== FINAL RESULTS ===")
        print(f"Total parks returned: {len(parks)}")
        
        for i, result in enumerate(parks[:5]):  # Show first 5
            name = result['park'].get('name', 'Unknown')
            print(f"{i+1}. {name} (Total time: {result['total_time']:.2f}h)")
            
        if len(parks) > 5:
            print(f"... and {len(parks) - 5} more parks")
    else:
        print("Cache file not found")

if __name__ == "__main__":
    main()