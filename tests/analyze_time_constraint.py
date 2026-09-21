#!/usr/bin/env python3

# Simple test to verify time constraint works properly
import subprocess

# Run the existing test script that we know works
result = subprocess.run(['python3', '/home/dweeks/ham_radio_src/PotaTrip/test_time_constraint.py'], 
                       capture_output=True, text=True, cwd='/home/dweeks/ham_radio_src/PotaTrip')

print("=== TIME CONSTRAINT TEST RESULTS ===")
print("Command:", "python3 /home/dweeks/ham_radio_src/PotaTrip/test_time_constraint.py")
print("Return code:", result.returncode)
print()
print("STDOUT:")
print(result.stdout)
if result.stderr:
    print("STDERR:")
    print(result.stderr)

print()
print("=== ANALYSIS ===")
print("The algorithm should be filtering parks based on time constraint.")
print("With a 6-hour limit, only a few parks should be returned, not 101.")
print("The fact that 101 parks are returned indicates that the time constraint is not working properly.")