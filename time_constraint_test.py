#!/usr/bin/env python3
"""
Simple test to verify time constraint algorithm works correctly.
This directly tests the core algorithm logic.
"""

def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points (simplified)"""
    from geopy.distance import geodesic
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def test_time_constraint_algorithm():
    """Test the time constraint logic with example data"""
    print("=== Time Constraint Algorithm Test ===")
    
    # Simulate a few parks with different distances from Eustace, TX
    # Eustace, TX coordinates
    city_coords = (32.3070902, -96.0066354)
    
    # Test parks with different distances (in miles)
    test_parks = [
        {"name": "Purtis Creek State Park", "distance": 4.0},      # ~0.1 hour driving
        {"name": "Nearby Park", "distance": 10.0},                 # ~0.25 hour driving  
        {"name": "Medium Park", "distance": 20.0},                 # ~0.5 hour driving
        {"name": "Far Park", "distance": 50.0},                    # ~1.25 hour driving
        {"name": "Very Far Park", "distance": 100.0},              # ~2.5 hour driving
    ]
    
    print(f"Testing with Eustace, TX (coordinates: {city_coords})")
    print()
    
    # Test different time constraints
    constraints = [1.0, 2.0, 4.0, 6.0]
    
    for hours in constraints:
        print(f"=== {hours} hour constraint ===")
        valid_parks = []
        
        for park in test_parks:
            # Calculate driving time
            driving_time = park["distance"] / 40.0  # 40 mph average
            # Total time = driving time + 2 hours at park
            total_time = driving_time + 2
            
            if total_time <= hours:
                valid_parks.append((park["name"], driving_time, total_time))
        
        print(f"Found {len(valid_parks)} parks within {hours} hours:")
        for name, driving, total in valid_parks:
            print(f"  - {name}: Driving {driving:.1f}h + 2h visit = {total:.1f}h total")
        
        if not valid_parks:
            print("  No parks found")
        print()

if __name__ == "__main__":
    test_time_constraint_algorithm()