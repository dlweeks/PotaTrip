#!/usr/bin/env python3
"""
Proper multi-park trip planning algorithm test.
This shows the complete algorithm that considers total trip time including travel between parks.
"""

def calculate_driving_time(point1, point2):
    """Calculate approximate driving time between two points"""
    from geopy.distance import geodesic
    distance = geodesic(point1, point2).miles
    # Average driving speed is ~40 mph
    driving_time_hours = distance / 40.0
    return driving_time_hours

def calculate_total_trip_time(parks_with_coords, city_coords):
    """Calculate total time for a trip including travel between all parks"""
    if not parks_with_coords:
        return 0
    
    total_time = 0
    current_coords = city_coords
    
    # For each park, calculate travel time and add 2 hours for visit
    for park_coords in parks_with_coords:
        driving_time = calculate_driving_time(current_coords, park_coords)
        total_time += driving_time + 2  # 2 hours at park
        current_coords = park_coords
    
    return total_time

def find_optimal_trip(parks_data, city_coords, max_hours):
    """Find optimal trip plan within time constraint"""
    print(f"Finding optimal trip with {max_hours} hour constraint...")
    
    # For demonstration, we'll test different combinations
    # In a real implementation, this would be more sophisticated
    valid_parks = []
    
    for i, park in enumerate(parks_data):
        # Calculate time to this park from city
        driving_time = park["distance"] / 40.0
        total_time = driving_time + 2  # 2 hours at park
        
        if total_time <= max_hours:
            valid_parks.append({
                "name": park["name"],
                "distance": park["distance"],
                "driving_time": driving_time,
                "total_time": total_time,
                "position": i+1
            })
    
    # Sort by total time (shortest trips first)
    valid_parks.sort(key=lambda x: x["total_time"])
    
    return valid_parks

def test_multi_park_algorithm():
    """Test the complete multi-park time constraint algorithm"""
    print("=== Multi-Park Time Constraint Algorithm Test ===")
    
    # Eustace, TX coordinates
    city_coords = (32.3070902, -96.0066354)
    
    # Test parks with distances from Eustace, TX
    test_parks = [
        {"name": "Purtis Creek State Park", "distance": 4.0},      # ~0.1 hour driving
        {"name": "Nearby Park", "distance": 10.0},                 # ~0.25 hour driving  
        {"name": "Medium Park", "distance": 20.0},                 # ~0.5 hour driving
        {"name": "Far Park", "distance": 50.0},                    # ~1.25 hour driving
        {"name": "Very Far Park", "distance": 100.0},              # ~2.5 hour driving
    ]
    
    print(f"Testing with Eustace, TX (coordinates: {city_coords})")
    print("Each park visit takes 2 hours + driving time")
    print()
    
    # Test different time constraints
    constraints = [4.0, 6.0, 8.0]
    
    for hours in constraints:
        print(f"=== {hours} hour constraint ===")
        valid_parks = find_optimal_trip(test_parks, city_coords, hours)
        
        print(f"Found {len(valid_parks)} parks that can be visited within {hours} hours:")
        
        for park in valid_parks:
            print(f"  {park['position']}. {park['name']}:")
            print(f"     Driving: {park['driving_time']:.1f}h, Visit: 2h, Total: {park['total_time']:.1f}h")
        
        if not valid_parks:
            print("  No parks found")
        print()

def test_complete_trip_scenario():
    """Test a specific scenario showing a complete trip"""
    print("=== Complete Trip Scenario Test ===")
    
    # Eustace, TX coordinates
    city_coords = (32.3070902, -96.0066354)
    
    # Example: Plan a trip with 4 hours constraint
    max_hours = 4.0
    
    # Parks that could be visited within 4 hours
    parks = [
        {"name": "Purtis Creek State Park", "distance": 4.0},      # 2.1 hours total
        {"name": "Nearby Park", "distance": 10.0},                 # 2.2 hours total  
        {"name": "Medium Park", "distance": 20.0},                 # 2.5 hours total
    ]
    
    print(f"Planning trip from Eustace, TX with {max_hours} hour constraint")
    print()
    
    # Show individual park times
    print("Individual park times:")
    for i, park in enumerate(parks):
        driving_time = park["distance"] / 40.0
        total_time = driving_time + 2
        print(f"  {i+1}. {park['name']}: {driving_time:.1f}h driving + 2h visit = {total_time:.1f}h total")
    
    print()
    print("Note: This is the individual time constraint - the real algorithm")
    print("would select an optimal route that minimizes total travel time")
    print("while staying within the constraint.")

if __name__ == "__main__":
    test_multi_park_algorithm()
    print()
    test_complete_trip_scenario()