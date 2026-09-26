#!/usr/bin/python3
"""
Complete Flask backend for POTA Trip Planner with proper time constraint algorithm
Based on working algorithm from HoursTrip/pota_final_trip.py
"""
from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import sys
import os
import logging
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import requests
from datetime import datetime, timedelta
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/pota_trip_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Cache management functions
def get_cache_file():
    """Get the cache file path"""
    return "/tmp/pota_parks_cache.csv"

def is_cache_valid():
    """Check if cache file exists and is less than 7 days old"""
    cache_file = get_cache_file()
    if not os.path.exists(cache_file):
        return False
    
    # Check file modification time
    mod_time = os.path.getmtime(cache_file)
    mod_datetime = datetime.fromtimestamp(mod_time)
    seven_days_ago = datetime.now() - timedelta(days=7)
    
    return mod_datetime > seven_days_ago

def load_parks_from_cache():
    """Load parks from cached CSV file or download fresh if needed"""
    try:
        cache_file = get_cache_file()
        
        # First, try to load from cache
        if os.path.exists(cache_file) and is_cache_valid():
            df = pd.read_csv(cache_file)
            logger.info(f"Loaded {len(df)} parks from cache")
            return df
        else:
            logger.info("Cache not valid or doesn't exist, downloading fresh data...")
            # Download the full park database
            url = "https://pota.app/all_parks_ext.csv"
            df = pd.read_csv(url)
            
            # Save to cache file
            df.to_csv(cache_file, index=False)
            logger.info(f"Downloaded and cached {len(df)} parks")
            return df
            
    except Exception as e:
        logger.error(f"Error in load_parks_from_cache: {e}")
        # Try to load cached data even if it's old or corrupted
        try:
            if os.path.exists(cache_file):
                df = pd.read_csv(cache_file)
                logger.info(f"Loaded {len(df)} parks from stale cache")
                return df
        except Exception as e2:
            logger.error(f"Error loading stale cache: {e2}")
            # Return empty DataFrame to prevent crashes, but log the error
            return pd.DataFrame()

def geocode_city(city_name, state_or_province=None, country=None):
    """
    Convert city name to lat/lng coordinates with international support
    Works with city, state/province, country format
    """
    try:
        # Build full location string for geocoding
        location_string = city_name
        if state_or_province:
            location_string += f", {state_or_province}"
        if country:
            location_string += f", {country}"
            
        # Use Nominatim geocoder (OpenStreetMap)
        geolocator = Nominatim(user_agent="potatrip")
        location = geolocator.geocode(location_string)
        
        if location:
            return (location.latitude, location.longitude)
        else:
            logger.warning(f"Could not geocode location: {location_string}")
            return None
    except Exception as e:
        logger.error(f"Error geocoding city: {e}")
        return None

def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points"""
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def find_nearby_parks(parks_df, city_coords, max_distance_miles=100, max_hours=None, max_miles=None):
    """Find parks within specified constraints"""
    nearby_parks = []
    
    # Check if we have data
    if parks_df.empty:
        return []
    
    # Apply distance constraint first to reduce the dataset
    if max_distance_miles is not None and max_distance_miles > 0:
        # Filter by radius first
        filtered_parks = []
        for index, park in parks_df.iterrows():
            if 'latitude' in park and 'longitude' in park:
                if not pd.isna(park['latitude']) and not pd.isna(park['longitude']):
                    try:
                        # Safely extract coordinates as scalars
                        lat = float(park['latitude'])
                        lon = float(park['longitude'])
                        park_coords = (lat, lon)
                        
                        distance = geodesic(city_coords, park_coords).miles
                        
                        # If this park is within the distance constraint, add it
                        if distance <= max_distance_miles:
                            park['distance_miles'] = distance
                            filtered_parks.append(park)
                    except Exception as e:
                        # Skip invalid coordinates
                        continue
        
        # Sort by distance (nearest to farthest)
        filtered_parks.sort(key=lambda x: x.get('distance_miles', 0))
        
        # Now apply time or distance constraints to filtered list
        if max_hours is not None and max_hours > 0:
            # Apply time constraint - prioritize by time (shorter trip times first)
            for park in filtered_parks:
                if 'latitude' in park and 'longitude' in park:
                    try:
                        # Safely extract coordinates as scalars
                        lat = float(park['latitude'])
                        lon = float(park['longitude'])
                        park_coords = (lat, lon)
                        
                        # Calculate time to park
                        driving_time = calculate_driving_time(city_coords, park_coords)
                        # Time constraint: 2 hours at park + driving time
                        total_time = driving_time + 2  # 2 hours at park + driving time
                        
                        # If this park can be visited within the time limit, add it
                        if total_time <= max_hours:
                            nearby_parks.append(park)
                    except Exception as e:
                        # Skip invalid coordinates
                        continue
                        
        elif max_miles is not None and max_miles > 0:
            # Apply miles constraint - prioritize by distance (shorter round trips first)
            for park in filtered_parks:
                if 'latitude' in park and 'longitude' in park:
                    try:
                        # Safely extract coordinates as scalars
                        lat = float(park['latitude'])
                        lon = float(park['longitude'])
                        park_coords = (lat, lon)
                        
                        # Calculate round trip distance
                        driving_time = calculate_driving_time(city_coords, park_coords)
                        round_trip_miles = driving_time * 40  # assuming 40 mph average
                        
                        # If this park fits within the miles constraint, add it
                        if round_trip_miles <= max_miles:
                            nearby_parks.append(park)
                    except Exception as e:
                        # Skip invalid coordinates
                        continue
        else:
            # No time or distance constraint, return filtered parks
            nearby_parks = filtered_parks
            
    else:
        # No radius constraint, apply time or distance constraints directly
        if max_hours is not None and max_hours > 0:
            # Apply time constraint to all parks
            for index, park in parks_df.iterrows():
                if 'latitude' in park and 'longitude' in park:
                    if not pd.isna(park['latitude']) and not pd.isna(park['longitude']):
                        try:
                            # Safely extract coordinates as scalars
                            lat = float(park['latitude'])
                            lon = float(park['longitude'])
                            park_coords = (lat, lon)
                            
                            # Calculate time to park
                            driving_time = calculate_driving_time(city_coords, park_coords)
                            # Time constraint: 2 hours at park + driving time
                            total_time = driving_time + 2  # 2 hours at park + driving time
                            
                            # If this park can be visited within the time limit, add it
                            if total_time <= max_hours:
                                nearby_parks.append(park)
                        except Exception as e:
                            # Skip invalid coordinates
                            continue
                            
        elif max_miles is not None and max_miles > 0:
            # Apply miles constraint to all parks
            for index, park in parks_df.iterrows():
                if 'latitude' in park and 'longitude' in park:
                    if not pd.isna(park['latitude']) and not pd.isna(park['longitude']):
                        try:
                            # Safely extract coordinates as scalars
                            lat = float(park['latitude'])
                            lon = float(park['longitude'])
                            park_coords = (lat, lon)
                            
                            # Calculate round trip distance
                            driving_time = calculate_driving_time(city_coords, park_coords)
                            round_trip_miles = driving_time * 40  # assuming 40 mph average
                            
                            # If this park fits within the miles constraint, add it
                            if round_trip_miles <= max_miles:
                                nearby_parks.append(park)
                        except Exception as e:
                            # Skip invalid coordinates
                            continue
        else:
            # No constraints, return all parks
            nearby_parks = parks_df.to_dict('records')
    
    # Log selected parks for debugging (only when time constraint is used)
    if max_hours is not None and len(nearby_parks) > 0:
        logger.info(f"\n=== SELECTED PARKS FOR {max_hours} HOUR CONSTRAINT ===")
        # Only show first 10 for brevity, but show the actual count
        for i, park in enumerate(nearby_parks[:10]):  # Show top 10 only
            name = park.get('name', 'Unknown')
            logger.info(f"{i+1}. {name}")
        logger.info(f"Total parks selected: {len(nearby_parks)}")
        logger.info("==========================================\n")
    
    return nearby_parks

def calculate_total_trip_time(parks, city_coords):
    """Calculate the total time for a trip including travel between parks"""
    if len(parks) <= 1:
        return 0
    
    total_time = 0
    current_coords = city_coords
    
    # For each park, calculate travel time and add 2 hours for visit
    for park in parks:
        if 'latitude' in park and 'longitude' in park:
            park_coords = (float(park['latitude']), float(park['longitude']))
            driving_time = calculate_driving_time(current_coords, park_coords)
            total_time += driving_time + 2  # 2 hours at park
            current_coords = park_coords
    
    return total_time

def generate_google_maps_url_with_markers(city, parks):
    """Generate Google Maps URL with park number markers using proper labeling"""
    try:
        # Create a better URL with proper labeling for each park
        base_url = "https://www.google.com/maps/dir/?api=1"
        
        # Add origin
        origin = city.replace(' ', '+')
        base_url += f"&origin={origin}"
        
        # Add destination (same as origin for circular route)
        base_url += f"&destination={origin}"
        
        # Add waypoints with proper labels for each park
        waypoints = []
        markers = []
        
        for i, park in enumerate(parks[:10]):  # Limit to first 10 parks
            if 'latitude' in park and 'longitude' in park:
                lat = park['latitude']
                lng = park['longitude']
                # Format as lat,lng for Google Maps
                waypoints.append(f"{lat},{lng}")
                
                # Add marker for this specific park with label
                marker_label = str(i + 1)  # Park numbers 1, 2, 3...
                markers.append(f"markers=label:{marker_label}%7C{lat},{lng}")
        
        if waypoints:
            waypoints_str = '|'.join(waypoints)
            base_url += f"&waypoints={waypoints_str}"
        
        # Add markers to the URL
        if markers:
            markers_str = '|'.join(markers)
            base_url += f"&map_action=overlay&overlay={markers_str}"
        
        logger.info(f"Generated Google Maps URL: {base_url}")
        return base_url
        
    except Exception as e:
        logger.error(f"Error generating Google Maps URL with markers: {e}")
        return "https://www.google.com/maps"

def generate_optimized_trip(parks, city_coords, max_hours=None, max_miles=None):
    """
    Generate an optimized trip that visits parks in logical order.
    This implements the core logic for the trip planner.
    """
    if not parks:
        return []
    
    # For time constraint, we want to build a trip that fits within the time limit
    if max_hours is not None:
        # We'll build a trip by adding parks one by one until we exceed the time limit
        selected_parks = []
        current_coords = city_coords
        total_time = 0
        
        # Sort parks by distance to start (nearest first) for better route optimization
        sorted_parks = sorted(parks, key=lambda x: x.get('distance_miles', 0))
        
        # Add parks to trip one by one until time limit is reached
        for park in sorted_parks:
            if 'latitude' in park and 'longitude' in park:
                try:
                    park_coords = (float(park['latitude']), float(park['longitude']))
                    driving_time = calculate_driving_time(current_coords, park_coords)
                    total_time += driving_time + 2  # 2 hours at park
                    
                    if total_time <= max_hours:
                        selected_parks.append(park)
                        current_coords = park_coords
                    else:
                        break  # We've exceeded the time limit
                except Exception as e:
                    # Skip invalid coordinates
                    continue
        return selected_parks
    
    # For miles constraint, we'll just return the first N parks that fit within the distance limit
    if max_miles is not None:
        selected_parks = []
        total_distance = 0
        
        # Sort parks by distance to start (nearest first) for better route optimization
        sorted_parks = sorted(parks, key=lambda x: x.get('distance_miles', 0))
        
        for park in sorted_parks:
            if 'latitude' in park and 'longitude' in park:
                try:
                    park_coords = (float(park['latitude']), float(park['longitude']))
                    distance = geodesic(city_coords, park_coords).miles
                    round_trip = distance * 2  # Round trip
                    
                    if total_distance + round_trip <= max_miles:
                        selected_parks.append(park)
                        total_distance += round_trip
                    else:
                        break  # We've exceeded the distance limit
                except Exception as e:
                    # Skip invalid coordinates
                    continue
        return selected_parks
    
    # For radius constraint, return all parks within radius
    return parks

# HTML template for the main page with enhanced UI
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POTA Trip Planner - Plan Your Ham Radio Adventures!</title>
    <style>
        :root {
            --bg-color: #f5f5f5;
            --container-bg: white;
            --text-color: #333;
            --header-color: #2c5aa0;
            --button-bg: #2c5aa0;
            --button-hover: #1a3d7a;
            --result-bg: #d4edda;
            --error-bg: #fff3cd;
            --border-color: #ddd;
            --park-item-bg: #e9ecef;
            --map-bg: #f0f0f0;
            --accent-color-1: #e74c3c;
            --accent-color-2: #3498db;
            --accent-color-3: #2ecc71;
            --sidebar-bg: rgba(44, 90, 160, 0.9);
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
        }

        .dark-mode {
            --bg-color: #1a1a1a;
            --container-bg: #2d2d2d;
            --text-color: #f0f0f0;
            --header-color: #4a7bff;
            --button-bg: #4a7bff;
            --button-hover: #3a6be0;
            --result-bg: #2d5a2d;
            --error-bg: #ffd700;
            --border-color: #444;
            --park-item-bg: #3d3d3d;
            --map-bg: #333;
            --accent-color-1: #ff6b6b;
            --accent-color-2: #64b5f6;
            --accent-color-3: #66bb6a;
            --sidebar-bg: rgba(74, 123, 255, 0.9);
            --success-color: #4caf50;
            --warning-color: #ffd54f;
            --danger-color: #f44336;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s, color 0.3s;
            background-image: url('https://images.unsplash.com/photo-1501854140801-50d01698950b?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1770&q=80');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }

        .container {
            display: flex;
            background-color: var(--container-bg);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
            transition: background-color 0.3s, color 0.3s;
            backdrop-filter: blur(10px);
        }

        .sidebar {
            width: 250px;
            background: var(--sidebar-bg);
            color: white;
            padding: 25px;
            height: fit-content;
        }

        .main-content {
            flex: 1;
            padding: 30px;
        }

        .title-container {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(90deg, var(--accent-color-1), var(--accent-color-2), var(--accent-color-3));
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(231, 76, 60, 0); }
            100% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0); }
        }

        h1 {
            color: white;
            margin: 0;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .subtitle {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1.2em;
            margin-top: 5px;
        }

        .instructions {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }

        .instructions h3 {
            margin-top: 0;
            color: white;
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
            padding-bottom: 8px;
        }

        .instructions ul {
            padding-left: 20px;
        }

        .instructions li {
            margin-bottom: 10px;
            line-height: 1.4;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--header-color);
        }

        input[type="text"], input[type="number"], select {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            box-sizing: border-box;
            background-color: var(--container-bg);
            color: var(--text-color);
            font-size: 16px;
            transition: border-color 0.3s, box-shadow 0.3s;
        }

        input[type="text"]:focus, input[type="number"]:focus, select:focus {
            border-color: var(--accent-color-2);
            box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.2);
            outline: none;
        }

        button {
            background: linear-gradient(90deg, var(--button-bg), #3a6be0);
            color: white;
            padding: 14px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 18px;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(44, 90, 160, 0.3);
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(44, 90, 160, 0.4);
        }

        .result {
            margin-top: 30px;
            padding: 25px;
            border-radius: 10px;
            display: none;
            background-color: var(--result-bg);
            color: #155724;
            border-left: 5px solid var(--accent-color-3);
            animation: fadeIn 0.5s;
        }

        .result h2 {
            color: var(--text-color);
            margin-top: 0;
        }

        .result .park-name {
            color: var(--text-color);
        }

        .result .park-reference {
            color: var(--accent-color-2);
        }

        .result .park-number {
            color: var(--accent-color-3);
        }

        .result .park-distance {
            background-color: var(--accent-color-1);
            color: white;
        }

        .result .error {
            color: #721c24;
            background-color: var(--error-bg);
            border-left-color: var(--accent-color-1);
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
        }

        .dark-mode .result .error {
            color: #721c24;
            background-color: var(--error-bg);
            border-left-color: var(--accent-color-1);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .error {
            background-color: var(--error-bg);
            color: #721c24;
            border-left-color: var(--accent-color-1);
        }

        .park-list {
            margin-top: 20px;
        }

        .park-item {
            padding: 15px;
            margin: 10px 0;
            background-color: var(--park-item-bg);
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: transform 0.2s, box-shadow 0.2s;
            border-left: 4px solid var(--accent-color-3);
        }

        .park-item:hover {
            transform: translateX(5px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }

        .park-info {
            flex: 1;
        }

        .park-number {
            font-weight: bold;
            color: var(--accent-color-3);
            font-size: 1.2em;
            margin-right: 10px;
        }

        .park-name {
            font-weight: 600;
            font-size: 1.1em;
            color: var(--text-color);
        }

        .park-reference {
            color: var(--accent-color-2);
            font-weight: 500;
        }

        .park-distance {
            background-color: var(--accent-color-1);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-weight: 600;
        }

        .google-maps-link {
            display: block;
            margin-top: 20px;
            padding: 15px;
            background: linear-gradient(90deg, var(--accent-color-2), var(--accent-color-3));
            color: white;
            text-align: center;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
        }

        .google-maps-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4);
        }

        .dark-mode-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            background-color: var(--button-bg);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            z-index: 100;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }

        .dark-mode-toggle:hover {
            background-color: var(--button-hover);
        }

        .park-number-marker {
            display: inline-block;
            width: 24px;
            height: 24px;
            background-color: var(--accent-color-1);
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-size: 12px;
            font-weight: bold;
            margin-right: 10px;
        }

        .park-item {
            display: flex;
            align-items: center;
        }

        .park-item .park-info {
            flex: 1;
        }

        .park-item .park-distance {
            margin-left: 15px;
        }
    </style>
</head>
<body>
    <button class="dark-mode-toggle" onclick="toggleDarkMode()">Toggle Dark Mode</button>
    
    <div class="container">
        <div class="sidebar">
            <div class="instructions">
                <h3>How to Use</h3>
                <ul>
                    <li>Enter a city name</li>
                    <li>Select your state/province</li>
                    <li>Set radius in miles (default 100)</li>
                    <li>Optionally set hours or miles limits</li>
                    <li>Click "Plan My Trip"</li>
                    <li>View results and Google Maps route</li>
                </ul>
            </div>
            
            <div class="instructions">
                <h3>Features</h3>
                <ul>
                    <li>Worldwide POTA parks</li>
                    <li>Dark/light mode toggle</li>
                    <li>Google Maps integration</li>
                    <li>Time constraint support</li>
                    <li>Distance filtering</li>
                    <li>Multiple filtering options</li>
                </ul>
            </div>
            
            <div class="instructions">
                <h3>Pro Tips</h3>
                <ul>
                    <li>Try "Eustace, TX" with 4 hours</li>
                    <li>Use "100 miles" for wide coverage</li>
                    <li>Set hours to limit travel time</li>
                    <li>Check Google Maps for directions</li>
                </ul>
            </div>
        </div>
        
        <div class="main-content">
            <div class="title-container">
                <h1>🚀 POTA Trip Planner</h1>
                <div class="subtitle">Plan Your Ham Radio Adventures Worldwide!</div>
            </div>
            
            <form id="tripForm">
                <div class="form-group">
                    <label for="city">City:</label>
                    <input type="text" id="city" name="city" required>
                </div>
                
                <div class="form-group">
                    <label for="state">State/Province:</label>
                    <select id="state" name="state" required>
                        <option value="">Select a location</option>
                        <option value="US-AL">Alabama (AL)</option>
                        <option value="US-AK">Alaska (AK)</option>
                        <option value="US-AZ">Arizona (AZ)</option>
                        <option value="US-AR">Arkansas (AR)</option>
                        <option value="US-CA">California (CA)</option>
                        <option value="US-CO">Colorado (CO)</option>
                        <option value="US-CT">Connecticut (CT)</option>
                        <option value="US-DE">Delaware (DE)</option>
                        <option value="US-FL">Florida (FL)</option>
                        <option value="US-GA">Georgia (GA)</option>
                        <option value="US-HI">Hawaii (HI)</option>
                        <option value="US-ID">Idaho (ID)</option>
                        <option value="US-IL">Illinois (IL)</option>
                        <option value="US-IN">Indiana (IN)</option>
                        <option value="US-IA">Iowa (IA)</option>
                        <option value="US-KS">Kansas (KS)</option>
                        <option value="US-KY">Kentucky (KY)</option>
                        <option value="US-LA">Louisiana (LA)</option>
                        <option value="US-ME">Maine (ME)</option>
                        <option value="US-MD">Maryland (MD)</option>
                        <option value="US-MA">Massachusetts (MA)</option>
                        <option value="US-MI">Michigan (MI)</option>
                        <option value="US-MN">Minnesota (MN)</option>
                        <option value="US-MS">Mississippi (MS)</option>
                        <option value="US-MO">Missouri (MO)</option>
                        <option value="US-MT">Montana (MT)</option>
                        <option value="US-NE">Nebraska (NE)</option>
                        <option value="US-NV">Nevada (NV)</option>
                        <option value="US-NH">New Hampshire (NH)</option>
                        <option value="US-NJ">New Jersey (NJ)</option>
                        <option value="US-NM">New Mexico (NM)</option>
                        <option value="US-NY">New York (NY)</option>
                        <option value="US-NC">North Carolina (NC)</option>
                        <option value="US-ND">North Dakota (ND)</option>
                        <option value="US-OH">Ohio (OH)</option>
                        <option value="US-OK">Oklahoma (OK)</option>
                        <option value="US-OR">Oregon (OR)</option>
                        <option value="US-PA">Pennsylvania (PA)</option>
                        <option value="US-RI">Rhode Island (RI)</option>
                        <option value="US-SC">South Carolina (SC)</option>
                        <option value="US-SD">South Dakota (SD)</option>
                        <option value="US-TN">Tennessee (TN)</option>
                        <option value="US-TX">Texas (TX)</option>
                        <option value="US-UT">Utah (UT)</option>
                        <option value="US-VT">Vermont (VT)</option>
                        <option value="US-VA">Virginia (VA)</option>
                        <option value="US-WA">Washington (WA)</option>
                        <option value="US-WV">West Virginia (WV)</option>
                        <option value="US-WI">Wisconsin (WI)</option>
                        <option value="US-WY">Wyoming (WY)</option>
                        <option value="CA-AB">Alberta (AB)</option>
                        <option value="CA-BC">British Columbia (BC)</option>
                        <option value="CA-MB">Manitoba (MB)</option>
                        <option value="CA-NB">New Brunswick (NB)</option>
                        <option value="CA-NL">Newfoundland and Labrador (NL)</option>
                        <option value="CA-NS">Nova Scotia (NS)</option>
                        <option value="CA-NT">Northwest Territories (NT)</option>
                        <option value="CA-NU">Nunavut (NU)</option>
                        <option value="CA-ON">Ontario (ON)</option>
                        <option value="CA-PE">Prince Edward Island (PE)</option>
                        <option value="CA-QC">Quebec (QC)</option>
                        <option value="CA-SK">Saskatchewan (SK)</option>
                        <option value="CA-YT">Yukon (YT)</option>
                        <option value="Other">Other (enter manually)</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="radius">Radius (miles):</label>
                    <input type="number" id="radius" name="radius" value="100" min="1">
                </div>
                
                <div class="form-group">
                    <label for="hours">Hours (optional):</label>
                    <input type="number" id="hours" name="hours" step="0.1" min="0">
                </div>
                
                <div class="form-group">
                    <label for="miles">Trip Miles (optional):</label>
                    <input type="number" id="miles" name="miles" step="0.1" min="0">
                </div>
                
                <button type="submit">Plan My Trip</button>
            </form>
            
            <div id="result" class="result">
                <h2>Results for <span id="resultCity"></span></h2>
                <div id="resultContent"></div>
                <a id="mapsLink" class="google-maps-link" href="#" target="_blank">View on Google Maps</a>
            </div>
        </div>
    </div>

    <script>
        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            const isDarkMode = document.body.classList.contains('dark-mode');
            localStorage.setItem('darkMode', isDarkMode);
        }

        // Check for saved theme preference
        document.addEventListener('DOMContentLoaded', function() {
            const savedDarkMode = localStorage.getItem('darkMode');
            if (savedDarkMode === 'true') {
                document.body.classList.add('dark-mode');
            }
        });

        document.getElementById('tripForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Clear previous results
            const resultDiv = document.getElementById('result');
            const resultContent = document.getElementById('resultContent');
            resultContent.innerHTML = '';
            resultDiv.style.display = 'none';
            
            const formData = new FormData(this);
            const data = {};
            for (let [key, value] of formData.entries()) {
                if (value.trim() !== '') {
                    data[key] = value;
                }
            }
            
            // Show loading state
            const submitButton = this.querySelector('button');
            const originalText = submitButton.textContent;
            submitButton.textContent = 'Processing...';
            submitButton.disabled = true;
            
            // Make API request
            fetch('/plan_trip', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                const resultCity = document.getElementById('resultCity');
                const resultContent = document.getElementById('resultContent');
                const mapsLink = document.getElementById('mapsLink');
                
                if (result.error) {
                    // Show error
                    resultContent.innerHTML = `<div class="error">${result.error}</div>`;
                    resultDiv.style.display = 'block';
                } else {
                    // Show results
                    resultCity.textContent = data.city;
                    let parksHTML = '<div class="park-list">';
                    result.parks.forEach((park, index) => {
                        parksHTML += `
                            <div class="park-item">
                                <div class="park-info">
                                    <span class="park-number-marker">${index + 1}</span>
                                    <span class="park-name">${park.name}</span>
                                    <br>
                                    <span class="park-reference">${park.reference}</span>
                                </div>
                                <div class="park-distance">${park.distance.toFixed(1)} miles</div>
                            </div>
                        `;
                    });
                    parksHTML += '</div>';
                    
                    resultContent.innerHTML = parksHTML;
                    mapsLink.href = result.googleMapsUrl;
                    resultDiv.style.display = 'block';
                }
            })
            .catch(error => {
                const resultContent = document.getElementById('resultContent');
                resultContent.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
                resultDiv.style.display = 'block';
            })
            .finally(() => {
                submitButton.textContent = originalText;
                submitButton.disabled = false;
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/plan_trip', methods=['POST'])
def plan_trip():
    try:
        data = request.get_json()
        
        city = data.get('city')
        state = data.get('state', 'US-TX')
        radius = data.get('radius', 100)
        hours = data.get('hours')
        miles = data.get('miles')
        
        # Validate that at least one constraint is provided
        if not hours and not miles and not radius:
            return jsonify({'error': 'Please provide at least one constraint (Hours, Miles, or Radius)'}), 400
        
        # Convert to numbers with proper error handling
        try:
            radius_value = float(radius) if radius else 100
        except (ValueError, TypeError):
            radius_value = 100
            
        try:
            hours_value = float(hours) if hours else None
        except (ValueError, TypeError):
            hours_value = None
            
        try:
            miles_value = float(miles) if miles else None
        except (ValueError, TypeError):
            miles_value = None
        
        # Log the request parameters
        logger.info(f"Planning trip for {city}, {state} with constraints: radius={radius_value}, hours={hours_value}, miles={miles_value}")
        
        # Load parks
        parks_df = load_parks_from_cache()
        if parks_df.empty:
            return jsonify({'error': 'Could not load park data. Please try again later.'}), 500
        
        # Geocode city
        city_coords = geocode_city(city, state)
        if not city_coords:
            return jsonify({'error': 'Could not find city coordinates. Please check the city name and try again.'}), 400
        
        # Find nearby parks with constraints
        if hours_value:
            nearby_parks = find_nearby_parks(parks_df, city_coords, max_hours=hours_value)
        elif miles_value:
            nearby_parks = find_nearby_parks(parks_df, city_coords, max_miles=miles_value)
        elif radius_value:
            nearby_parks = find_nearby_parks(parks_df, city_coords, max_distance_miles=radius_value)
        else:
            nearby_parks = find_nearby_parks(parks_df, city_coords)
        
        # Optimize the trip based on constraints
        if hours_value:
            optimized_parks = generate_optimized_trip(nearby_parks, city_coords, max_hours=hours_value)
            if optimized_parks:
                nearby_parks = optimized_parks
        elif miles_value:
            optimized_parks = generate_optimized_trip(nearby_parks, city_coords, max_miles=miles_value)
            if optimized_parks:
                nearby_parks = optimized_parks
        # Don't override nearby_parks if no optimization was done (it already contains the filtered results)
        
        # Generate Google Maps URL with markers
        google_maps_url = generate_google_maps_url_with_markers(city, nearby_parks)
        
        # Prepare response
        parks_data = []
        for park in nearby_parks:
            name = park.get('name', 'Unnamed Park')
            ref = park.get('reference', 'Unknown')
            distance = 0
            
            if 'latitude' in park and 'longitude' in park:
                park_coords = (float(park['latitude']), float(park['longitude']))
                distance = geodesic(city_coords, park_coords).miles
            
            parks_data.append({
                'name': name,
                'reference': ref,
                'distance': distance
            })
        
        response_data = {
            'city': city,
            'parkCount': len(parks_data),
            'parks': parks_data,
            'googleMapsUrl': google_maps_url
        }
        
        # Log the successful request
        logger.info(f"Successfully planned trip with {len(parks_data)} parks for {city}")
        
        return jsonify(response_data)
        
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Application error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Application error: {str(e)}'}), 500

if __name__ == '__main__':
    # Initialize cache on startup
    logger.info("Initializing POTA Trip Planner...")
    parks_df = load_parks_from_cache()
    logger.info(f"Loaded {len(parks_df)} parks from cache")
    logger.info("Starting POTA Trip Planner server...")
    logger.info("Visit http://localhost:5001 to use the application")
    app.run(host='0.0.0.0', port=5001, debug=True)