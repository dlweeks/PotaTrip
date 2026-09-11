# PotaTrip Web Application - Test Cases

## Test Suite Overview
This document contains comprehensive test cases for the PotaTrip web application to ensure all functionality works correctly.

## Test Case 1: Basic Functionality
**Test Case ID:** TC-001
**Description:** Verify basic application startup and form display
**Pre-conditions:** Application is running
**Steps:**
1. Navigate to http://localhost:5000
2. Verify the web form displays correctly
3. Check all input fields are present (City, State, Radius, Hours, Miles)
**Expected Results:** 
- Form loads successfully
- All input fields are visible and functional
- No JavaScript errors

## Test Case 2: Error Handling - Missing Required Fields
**Test Case ID:** TC-002
**Description:** Verify error handling when no constraints are provided
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Dallas" in City field
2. Enter "US-TX" in State field
3. Leave all constraint fields (Radius, Hours, Miles) blank
4. Click "Plan My Trip"
**Expected Results:** 
- Error message displayed: "Please provide at least one constraint (Hours, Miles, or Radius)"
- No trip calculation performed

## Test Case 3: Error Handling - Invalid Numeric Input
**Test Case ID:** TC-003
**Description:** Verify handling of invalid numeric input (the original "Could not convert string to float" issue)
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Eustace" in City field
2. Enter "US-TX" in State field
3. Enter "4" in Hours field (valid number)
4. Click "Plan My Trip"
**Expected Results:** 
- No crash or error
- Results displayed correctly showing Purtis Creek State Park (if within constraints)
- No "Could not convert string to float" error

## Test Case 4: Radius Filtering
**Test Case ID:** TC-004
**Description:** Verify radius-based filtering works correctly
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Dallas" in City field
2. Enter "US-TX" in State field
3. Enter "50" in Radius field
4. Click "Plan My Trip"
**Expected Results:** 
- Parks within 50 miles of Dallas are shown
- All parks are within the specified radius

## Test Case 5: Hours Filtering
**Test Case ID:** TC-005
**Description:** Verify hours-based filtering works correctly
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Eustace" in City field
2. Enter "US-TX" in State field
3. Enter "4" in Hours field
4. Click "Plan My Trip"
**Expected Results:** 
- Parks that can be visited within 4 hours total (driving + 2 hours at park) are shown
- Purtis Creek State Park should appear (as it's only ~4 miles away and 2.1 hours total)

## Test Case 6: Miles Filtering
**Test Case ID:** TC-006
**Description:** Verify miles-based filtering works correctly
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Austin" in City field
2. Enter "US-TX" in State field
3. Enter "200" in Miles field
4. Click "Plan My Trip"
**Expected Results:** 
- Parks with round-trip miles under 200 are shown
- All results have round-trip distances within limit

## Test Case 7: Cache Management
**Test Case ID:** TC-007
**Description:** Verify automatic cache management works correctly
**Pre-conditions:** Database is available, cache file exists
**Steps:**
1. Check if /tmp/pota_parks_cache.csv exists
2. Verify cache file is less than 5 days old
3. If cache is expired, verify automatic update occurs
**Expected Results:** 
- Cache file is properly managed
- Database updates automatically every 5 days
- No errors during cache operations

## Test Case 8: Google Maps Integration
**Test Case ID:** TC-008
**Description:** Verify Google Maps link generation works
**Pre-conditions:** Application is running with results
**Steps:**
1. Enter "Dallas" in City field
2. Enter "US-TX" in State field
3. Enter "100" in Radius field
4. Click "Plan My Trip"
5. Check for Google Maps link in results
**Expected Results:** 
- Google Maps URL is generated correctly
- Link opens in new tab when clicked
- Waypoints are properly formatted

## Test Case 9: Non-POTA Filtering
**Test Case ID:** TC-009
**Description:** Verify non-POTA parks are properly filtered out
**Pre-conditions:** Application is running
**Steps:**
1. Search for parks in a location that might have non-POTA parks
2. Check results
**Expected Results:** 
- Non-POTA parks (like "State Park Store") are excluded
- Only legitimate POTA parks are shown

## Test Case 10: Park Number Display
**Test Case ID:** TC-010
**Description:** Verify park reference numbers are displayed
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Dallas" in City field
2. Enter "US-TX" in State field
3. Enter "100" in Radius field
4. Click "Plan My Trip"
5. Check results for park reference numbers
**Expected Results:** 
- Park reference numbers are displayed (e.g., US-4423, US-6547)
- Numbers are properly formatted

## Test Case 11: Edge Case - Very Small Radius
**Test Case ID:** TC-011
**Description:** Verify behavior with very small radius
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Houston" in City field
2. Enter "US-TX" in State field
3. Enter "1" in Radius field
4. Click "Plan My Trip"
**Expected Results:** 
- Very few or no parks found (as expected)
- Appropriate error message if no parks found

## Test Case 12: Edge Case - Zero Hours
**Test Case ID:** TC-012
**Description:** Verify behavior with zero hours constraint
**Pre-conditions:** Application is running
**Steps:**
1. Enter "San Antonio" in City field
2. Enter "US-TX" in State field
3. Enter "0" in Hours field
4. Click "Plan My Trip"
**Expected Results:** 
- No parks found (as expected)
- Appropriate error message

## Test Case 13: Input Validation
**Test Case ID:** TC-013
**Description:** Verify all input fields properly validate data
**Pre-conditions:** Application is running
**Steps:**
1. Enter invalid data in numeric fields (text instead of numbers)
2. Enter valid data in all fields
3. Submit form
**Expected Results:** 
- Invalid numeric data is handled gracefully
- Valid data is processed correctly
- No crashes occur

## Test Case 14: Performance Test
**Test Case ID:** TC-014
**Description:** Verify application performance with large datasets
**Pre-conditions:** Application is running with full cache
**Steps:**
1. Enter a city with many nearby parks
2. Set a generous radius
3. Click "Plan My Trip"
**Expected Results:** 
- Results load within reasonable time (less than 5 seconds)
- All parks are properly sorted by distance
- No performance issues with large datasets

## Test Case 15: Cross-Browser Compatibility
**Test Case ID:** TC-015
**Description:** Verify application works across different browsers
**Pre-conditions:** Application is running
**Steps:**
1. Access application in Chrome, Firefox, Safari
2. Test all form functionality
3. Test all constraint options
**Expected Results:** 
- All browsers display and function correctly
- No browser-specific issues
- Consistent user experience

## Test Case 16: Dark Mode Toggle
**Test Case ID:** TC-016
**Description:** Verify dark mode functionality
**Pre-conditions:** Application is running
**Steps:**
1. Click "Toggle Dark Mode" button
2. Verify UI switches to dark theme
3. Click again to switch back to light theme
4. Verify preference is saved in localStorage
**Expected Results:** 
- Theme switches correctly between light and dark
- All UI elements adapt to the selected theme
- Preference persists between sessions

## Test Case 17: Worldwide Support
**Test Case ID:** TC-017
**Description:** Verify worldwide functionality works correctly
**Pre-conditions:** Application is running
**Steps:**
1. Enter "London" in City field
2. Enter "GB" in State field
3. Enter "100" in Radius field
4. Click "Plan My Trip"
**Expected Results:** 
- Application works with international locations
- Parks in London area are found
- No errors with international coordinates

## Test Case 18: International Park Numbers
**Test Case ID:** TC-018
**Description:** Verify international park reference numbers are displayed
**Pre-conditions:** Application is running
**Steps:**
1. Enter "Tokyo" in City field
2. Enter "JP" in State field
3. Enter "200" in Radius field
4. Click "Plan My Trip"
**Expected Results:** 
- International park reference numbers are displayed (e.g., JP-1234)
- Numbers are properly formatted for international parks
- All parks are properly filtered and displayed

## Test Case 19: Theme Preference Persistence
**Test Case ID:** TC-019
**Description:** Verify theme preference persists between sessions
**Pre-conditions:** Application is running
**Steps:**
1. Switch to dark mode
2. Refresh the page
3. Verify theme remains dark
**Expected Results:** 
- User preference is saved and restored
- Theme persists across page refreshes
- Respects OS preference by default

## Test Case 20: Responsive Design
**Test Case ID:** TC-020
**Description:** Verify application works on mobile devices
**Pre-conditions:** Application is running
**Steps:**
1. Access application on mobile device or browser in mobile view
2. Test all form functionality
3. Test dark mode toggle
**Expected Results:** 
- All UI elements are properly responsive
- Form fields are touch-friendly
- Dark mode toggle works on mobile
- No layout issues on small screens

## Test Execution Notes:
- All tests should be executed against the deployed application
- Test results should be documented in a test execution log
- Any failures should be logged and addressed before release
- Tests should be automated where possible for continuous integration