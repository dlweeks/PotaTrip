# POTA Trip Planner - Main Application

This is the main application file for the POTA Trip Planner web application.

## Overview

The app.py file contains the core Flask application that handles:
- Web interface rendering
- User input processing
- Trip planning algorithm execution
- Database interaction
- Error handling

## Key Components

### Flask Routes
- `/` - Main application page
- `/plan_trip` - Trip planning endpoint

### Functions
- `get_parks_nearby()` - Retrieves parks within a specified radius
- `calculate_time_constraints()` - Calculates time-based constraints
- `calculate_miles_constraints()` - Calculates mileage-based constraints
- `validate_input()` - Validates user input parameters

## Dependencies

This application requires the following Python packages:
- Flask
- pandas
- geopy
- requests

## Usage

Run the application with:
```bash
python3 app.py
```

Then visit `http://localhost:5000` in your web browser.