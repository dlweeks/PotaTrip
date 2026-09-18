#!/usr/bin/env python3
"""
Debug script to understand why Purtis Creek is not showing up in the results
"""
import sys
import os
import pandas as pd
from geopy.distance import geodesic

# Add the venv to the path for imports
sys.path.insert(0, '/home/dweeks/ham_radio_src/PotaTrip/venv/lib/python3.13/site-packages')

def debug_purtis_creek():
    """Debug why Purtis Creek doesn't appear in results"""
    print("Debugging Purtis Creek issue...")
    
    try:
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
        
        # Test with a specific city
        city_coords = (32.3537, -95.9936)  # This should be Purtis Creek's coordinates
        
        # Or let's try with a more realistic city like 'Eustace, TX'
        # But for debugging, let's just look at the data directly
        test_city = (32.3537, -95.9936)  # Purtis Creek coordinates
        
        print("\nTesting distance calculation:")
        for i, park in df.head(5).iterrows():
            if 'latitude' in park and 'longitude' in park:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(test_city, park_coords).miles
                print(f"{park['name']}: {distance:.2f} miles away")
                
        # Test with a more realistic city
        print("\nTesting with a known city - Eustace, TX")
        test_city_2 = (32.3537, -95.9936)  # Purtis Creek coordinates
        
        # Let's look at a few specific parks that might be closer
        print("\nLooking for closer parks to Purtis Creek:")
        for i, park in df.iterrows():
            if 'latitude' in park and 'longitude' in park:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(test_city_2, park_coords).miles
                if distance < 10:  # Show parks within 10 miles
                    print(f"{park['name']}: {distance:.2f} miles away")
        
        # Now let's look specifically for parks near the city
        print("\nSearching for parks around Purtis Creek coordinates...")
        purtis_coords = (32.3537, -95.9936)
        nearby_parks = []
        
        for i, park in df.iterrows():
            if 'latitude' in park and 'longitude' in park:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(purtis_coords, park_coords).miles
                
                # Check if this park is close to Purtis Creek
                if distance < 5:  # Within 5 miles
                    nearby_parks.append((park, distance))
        
        print(f"Found {len(nearby_parks)} parks within 5 miles of Purtis Creek:")
        for park, distance in nearby_parks:
            print(f"  {park['name']}: {distance:.2f} miles")
            
    except Exception as e:
        print(f"Error in debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_purtis_creek()