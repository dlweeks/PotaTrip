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

## Project Structure

This project follows a clean structure:
- `app.py` - Main web application
- `index.html` - Web interface
- `tests/` - Test cases and debugging tools
- `docs/` - Documentation

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

## Technical Details

1. Database Management System:
   - Weekly recreation of the parks database from pota.app
   - Caching mechanism that maintains database for up to a week
   - Automatic database refresh when older than 7 days
   - Proper cache file management

2. Web Interface:
   - Complete Flask web application with responsive UI
   - City input with state/province selection
   - Multiple constraint options (radius, hours, miles)
   - Google Maps integration with park markers
   - Dark/light mode toggle

3. Trip Planning Algorithms:
   - Radius filtering: Parks within specified distance
   - Hours filtering: Parks that can be visited within time constraints (2 hours at each park + driving time)
   - Miles filtering: Parks within specified round-trip distance limits

4. Logging & Debugging:
   - Comprehensive logging of user inputs and trip data
   - Server-side logging to /tmp/pota_trip_log.txt
   - Detailed debugging information

5. Test Coverage:
   - All three constraint algorithms thoroughly tested
   - Test cases for radius, hours, and miles constraints
   - Verification that algorithms work correctly in the main program

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