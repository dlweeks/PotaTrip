#!/usr/bin/python3
"""
Standalone test for the time constraint algorithm
"""

import pandas as pd
import sys
import os
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import requests

def get_cache_file():
    """Get the cache file path"""
    return "/tmp/pota_parks_cache.csv"

def load_parks_from_cache():
    """Load parks from cached CSV file"""
    try:
        cache_file = get_cache_file()
        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file)
            print(f"Loaded {len(df)} parks from cache")
            return df
        else:
            print("Cache file not found")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error loading cache: {e}")
        return pd.DataFrame()

def geocode_city(city_name):
    """Convert city name to lat/lng coordinates"""
    try:
        geolocator = Nominatim(user_agent="potatrip_test")
        location = geolocator.geocode(city_name)
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

def find_nearby_parks(parks_df, city_coords, max_distance_miles=100, max_hours=None, max_miles=None):
    """Find parks within specified constraints - FIXED VERSION"""
    nearby_parks = []
    
    # Check if we have data
    if parks_df.empty:
        return []
    
    # Filter out non-POTA parks and check distances
    for index, park in parks_df.iterrows():
        # Skip non-POTA parks (if any)
        if 'name' in park and ('State Park' in str(park['name']) or 'State Park Store' in str(park['name'])):
            continue
            
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
                        nearby_parks.append((park, distance, total_time))
                elif max_miles is not None:
                    # Check if total round trip is within limits
                    driving_time = calculate_driving_time(city_coords, park_coords)
                    round_trip_miles = driving_time * 40  # assuming 40 mph average
                    if round_trip_miles <= max_miles:
                        nearby_parks.append((park, distance, round_trip_miles))
                elif max_distance_miles is not None:
                    # Only distance constraint
                    if distance <= max_distance_miles:
                        nearby_parks.append((park, distance, 0))
    
    # Sort by time (if using time constraint) or distance
    if max_hours is not None:
        nearby_parks.sort(key=lambda x: x[2])  # Sort by total time
    else:
        nearby_parks.sort(key=lambda x: x[1])  # Sort by distance
    
    # Return just the parks (not distance/time info)
    return [park for park, _, _ in nearby_parks]

def main():
    print("Testing time constraint algorithm...")
    
    # Load parks
    parks_df = load_parks_from_cache()
    if parks_df.empty:
        print("Could not load park data")
        return
    
    # Test with Eustace, TX and 6 hours
    city = "Eustace"
    state = "US-TX"
    hours = 6
    
    print(f"Testing {city}, {state} with {hours} hours constraint...")
    
    # Geocode city
    city_coords = geocode_city(f"{city}, {state}")
    if not city_coords:
        print("Could not find city coordinates")
        return
    
    print(f"City coordinates: {city_coords}")
    
    # Find nearby parks with time constraint
    nearby_parks = find_nearby_parks(parks_df, city_coords, max_hours=hours)
    
    print(f"Found {len(nearby_parks)} parks within {hours} hours")
    
    # Show first few parks with their times
    for i, park in enumerate(nearby_parks[:5]):  # Show first 5
        if 'latitude' in park and 'longitude' in park:
            park_coords = (float(park['latitude']), float(park['longitude']))
            driving_time = calculate_driving_time(city_coords, park_coords)
            total_time = driving_time + 2
            print(f"{i+1}. {park.get('name', 'Unknown')} - Driving: {driving_time:.1f}h, Total: {total_time:.1f}h")
    
    if len(nearby_parks) > 5:
        print(f"... and {len(nearby_parks) - 5} more parks")

if __name__ == "__main__":
    main()