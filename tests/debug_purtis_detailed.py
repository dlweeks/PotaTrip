#!/usr/bin/env python3
"""
Debug why Purtis Creek is not appearing in results
"""
import sys
import os
import subprocess
import pandas as pd
from geopy.distance import geodesic

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def debug_purtis_creek_issue():
    """Debug why Purtis Creek is not showing up"""
    print("=== DEBUGGING PURTIS CREEK ISSUE ===")
    
    # Load the cache file
    cache_file = "/tmp/pota_parks_cache.csv"
    df = pd.read_csv(cache_file)
    print(f"Loaded {len(df)} parks from cache")
    
    # Find Purtis Creek specifically
    purtis_park = df[df['name'].str.contains('Purtis Creek', case=False, na=False)]
    print(f"Purtis Creek data: {purtis_park}")
    
    if not purtis_park.empty:
        park_row = purtis_park.iloc[0]
        print(f"Purtis Creek coordinates: {park_row['latitude']}, {park_row['longitude']}")
        print(f"Purtis Creek reference: {park_row['reference']}")
        
        # Test with a specific city that's likely to be closer to Purtis Creek
        # Let's try a city near Purtis Creek - Eustace, TX which should be near Purtis Creek
        test_city = (32.3537, -95.9936)  # Purtis Creek coordinates
        
        # Test with a small time constraint to see if it shows up
        print(f"\nTesting with city coordinates: {test_city}")
        
        # Test distance calculation to Purtis Creek
        purtis_coords = (float(park_row['latitude']), float(park_row['longitude']))
        distance = geodesic(test_city, purtis_coords).miles
        print(f"Distance to Purtis Creek: {distance:.2f} miles")
        
        # Try to get a few other parks near this area to see if they show up
        print("\nLooking for parks in the same area:")
        for i, park in df.iterrows():
            if 'latitude' in park and 'longitude' in park:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(test_city, park_coords).miles
                if distance < 5:  # Within 5 miles
                    print(f"  {park['name']}: {distance:.2f} miles away")
        
        print("\nThis suggests Purtis Creek should be included in results")
        
    else:
        print("Purtis Creek not found in cache")

if __name__ == "__main__":
    debug_purtis_creek_issue()