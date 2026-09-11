#!/usr/bin/env python3
"""
Test script to verify the PotaTrip application functionality
"""

import requests
import sys
import os

def test_application():
    """Test the application functionality"""
    print("Testing PotaTrip application...")
    
    # Test if the server is running
    try:
        response = requests.get('http://localhost:5001', timeout=5)
        print(f"Server status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Server is accessible")
        else:
            print(f"❌ Server returned error: {response.status_code}")
    except Exception as e:
        print(f"❌ Server not accessible: {e}")
        return False
    
    # Test the API endpoint with a simple case
    try:
        test_data = {
            'city': 'Eustace',
            'state': 'US-TX',
            'radius': 100
        }
        
        response = requests.post('http://localhost:5001/plan_trip', 
                               json=test_data,
                               timeout=30)
        print(f"API Test Result: {response.status_code}")
        if response.status_code == 200:
            print("✅ API is working")
            try:
                data = response.json()
                print(f"API Response: {data}")
            except:
                print("API returned non-JSON response")
                print(f"Response text: {response.text[:200]}...")
        else:
            print(f"❌ API Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ API Test Failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_application()
    sys.exit(0 if success else 1)