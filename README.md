# POTA Trip Planner

A web application for planning ham radio park visiting trips using the POTA (Parks on the Air) database.

## Features

- **Web Interface**: Easy-to-use form with input boxes for all parameters
- **Multiple Filtering Options**: 
  - Radius (miles) - filter parks within a certain distance
  - Maximum Hours - filter parks that can be visited within a time limit
  - Maximum Round-trip Miles - filter parks based on travel distance
- **Automatic CSV Caching**: Database updates automatically every 5 days
- **Google Maps Integration**: Embedded links to trip planning
- **Error Handling**: Proper validation to prevent "Could not convert string to float" errors

## Installation

1. Install required packages:
   ```bash
   pip3 install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python3 app.py
   ```

3. Visit `http://localhost:5000` in your web browser

## Usage

1. Enter a city name (e.g., "Eustace")
2. Enter a state/region code (e.g., "US-TX")
3. Set at least one constraint (Radius, Hours, or Miles)
4. Click "Plan My Trip"

## Example Usage

### Using Hours Constraint:
- City: "Eustace" 
- State: "US-TX"
- Hours: "4"
- This will find parks that can be visited within 4 hours total (including travel and 2 hours at each park)

### Using Radius Constraint:
- City: "Dallas"
- State: "US-TX"
- Radius: "50"
- This will find parks within 50 miles of Dallas

### Using Miles Constraint:
- City: "Austin"
- State: "US-TX"
- Miles: "200"
- This will find parks with round-trip distances under 200 miles

## Technical Details

- Uses the official POTA database from `https://pota.app/all_parks_ext.csv`
- Automatically caches data in `/tmp/pota_parks_cache.csv`
- Filters out non-POTA parks (like "State Park Store")
- Shows park reference numbers (e.g., US-4423, US-6547)
- Includes Google Maps integration for trip planning

## Error Handling

The application handles the following errors gracefully:
- "Could not convert string to float" - Fixed with proper input validation
- City not found - Shows appropriate error message
- No parks meeting criteria - Shows appropriate error message
- Database connection issues - Shows appropriate error message

## Requirements

- Flask
- pandas
- geopy
- requests