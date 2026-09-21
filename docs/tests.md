# Test Documentation

This directory contains all the test cases for the POTA Trip Planner application.

## Test Files Overview

### Main Test Files:
- `test_all_cases.py` - Comprehensive test covering all functionality
- `test_algorithm.py` - Tests for core algorithm implementations
- `test_time_constraint.py` - Tests specifically for time constraint calculations
- `test_direct.py` - Direct tests for specific functions
- `test_fix_verification.py` - Tests for fixes and verification
- `test_purtis_direct.py` - Direct tests for Purtis-related functionality
- `test_final_verification.py` - Final verification tests
- `test_cases.md` - Documentation of test cases and expected behavior

### Debug/Analysis Files:
- `debug_parks.py` - Debugging tool for park data
- `debug_time_calc.py` - Debugging tool for time calculations
- `debug_purtis.py` - Debugging tool for Purtis-related operations
- `debug_purtis_detailed.py` - Detailed debugging for Purtis operations
- `analyze_time_constraint.py` - Analysis of time constraint calculations
- `standalone_time_test.py` - Standalone time constraint testing
- `time_constraint_test.py` - Time constraint specific tests
- `multi_park_test.py` - Multi-park testing scenarios
- `comprehensive_test.py` - Comprehensive testing suite
- `final_test.py` - Final testing before deployment
- `final_test_fix.py` - Tests for specific fixes
- `final_verification.py` - Final verification tests
- `test_direct.py` - Direct function tests
- `test_fix_verification.py` - Verification of fixes
- `test_purtis_direct.py` - Direct Purtis tests
- `test_final_verification.py` - Final verification tests

## How to Run Tests

To run all tests:
```bash
cd tests/
python3 test_all_cases.py
```

For individual test files:
```bash
python3 test_algorithm.py
python3 test_time_constraint.py
```

## Test Structure

The tests follow a consistent structure:
1. Import necessary modules
2. Define test functions with descriptive names
3. Include assertions for expected behavior
4. Document test cases and expected outcomes

## Test Coverage

The tests cover:
- Algorithm correctness
- Time constraint calculations
- Input validation
- Error handling
- Database interaction
- Web interface integration