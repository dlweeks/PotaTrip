#!/usr/bin/env python3
"""
Standalone test program to demonstrate the time constraint algorithm.
This shows exactly how the time constraint should work in the POTA Trip Planner.
"""

import pandas as pd
import os
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

def load_parks():
    """Load parks from cache file"""
    cache_file = "/tmp/pota_parks_cache.csv"
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        print(f"Loaded {len(df)} parks from cache")
        return df
    else:
        print("Cache file not found")
        return pd.DataFrame()

def geocode_city(city_name, state_code):
    """Convert city name to lat/lng coordinates"""
    try:
        geolocator = Nominatim(user_agent="potatrip_test")
        location = geolocator.geocode(f"{city_name}, {state_code}")
        if location:
            return (location.latitude, location.longitude)
        else:
            return None
    except Exception as e:
        print(f"Error geocoding city: {e}")
        return None

def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points"""
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def find_nearby_parks(parks_df, city_coords, max_hours=None):
    """Find parks within time constraint (STANDALONE VERSION)"""
    nearby_parks = []
    
    # Check if we have data
    if parks_df.empty:
        return []
    
    print(f"Processing {len(parks_df)} parks with {max_hours} hour constraint...")
    
    # Just test with first few parks for demonstration
    test_count = min(100, len(parks_df))
    for index, park in parks_df.iloc[:test_count].iterrows():
        # Check if we have the coordinates
        if 'latitude' in park and 'longitude' in park:
            # Handle potential NaN values
            if pd.isna(park['latitude']) or pd.isna(park['longitude']):
                continue
                
            # Ensure latitude is within valid range
            if -90 <= float(park['latitude']) <= 90:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(city_coords, park_coords).miles
                
                # Apply time constraint
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
    
    return nearby_parks

def main():
    print("=== POTA Trip Planner Time Constraint Algorithm Test ===")
    print()
    
    # Load parks
    parks_df = load_parks()
    if parks_df.empty:
        print("Cannot proceed without park data")
        return
    
    # Test with Eustace, TX and different hour constraints
    city = "Eustace"
    state = "US-TX"
    
    print(f"Testing with {city}, {state}")
    
    # Geocode city
    city_coords = geocode_city(city, state)
    if not city_coords:
        print("Could not find city coordinates")
        return
    
    print(f"City coordinates: {city_coords}")
    print()
    
    # Test different time constraints
    constraints = [0.5, 1.0, 2.0, 4.0, 6.0, 8.0]
    
    for hours in constraints:
        print(f"=== Testing {hours} hour constraint ===")
        parks = find_nearby_parks(parks_df, city_coords, max_hours=hours)
        
        print(f"Found {len(parks)} parks within {hours} hours")
        
        # Show first 3 parks with their times
        for i, result in enumerate(parks[:3]):
            park = result['park']
            name = park.get('name', 'Unknown')
            driving = result['driving_time']
            total = result['total_time']
            print(f"  {i+1}. {name} - Driving: {driving:.1f}h, Total: {total:.1f}h")
        
        if len(parks) > 3:
            print(f"  ... and {len(parks) - 3} more parks")
        print()

if __name__ == "__main__":
    main()