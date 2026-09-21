# POTA Trip Planner - Tests

This directory contains all test cases and debugging tools for the POTA Trip Planner application.

## Overview

The tests directory is organized to separate testing code from the main application code. This provides:

1. **Clean separation** between application code and test code
2. **Easier maintenance** of the main application
3. **Better documentation** of testing procedures
4. **Improved code organization** for future development

## Test Categories

### Core Algorithm Tests
- `test_algorithm.py` - Tests for core trip planning algorithms
- `test_time_constraint.py` - Tests for time constraint calculations
- `test_all_cases.py` - Comprehensive test coverage

### Debugging and Analysis Tools
- `debug_parks.py` - Debugging park data operations
- `debug_time_calc.py` - Time calculation debugging
- `analyze_time_constraint.py` - Analysis of time constraint algorithms

### Verification and Final Tests
- `final_verification.py` - Final verification of functionality
- `test_final_verification.py` - Final verification test cases
- `comprehensive_test.py` - Complete test suite

## Running Tests

To run individual tests:
```bash
cd tests/
python3 test_algorithm.py
```

To run all tests:
```bash
python3 test_all_cases.py
```

## Test Documentation

See `test_cases.md` for detailed test case documentation and expected behaviors.