#!/bin/bash
# Test Runner Script for Backend Project

echo "=============================================================================="
echo "PROJECT TEST SUITE RUNNER"
echo "=============================================================================="
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo ""

# Check if pytest is available
echo "Checking pytest availability..."
if python -c "import pytest; print('pytest version:', pytest.__version__)" 2>/dev/null; then
    echo "✓ pytest is available"
else
    echo "✗ pytest is not available"
    exit 1
fi

echo ""
echo "=============================================================================="
echo "RUNNING PYTEST TEST SUITE"
echo "=============================================================================="

# Run pytest with basic options
python -m pytest tests/ -v --tb=short --maxfail=10 -x 2>&1 | tee test_results.txt

# Get the exit code
EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=============================================================================="
echo "TEST RESULTS SUMMARY"
echo "=============================================================================="

# Extract summary from pytest output
if grep -q "passed" test_results.txt; then
    echo "✓ Tests completed"
    grep -E "(passed|failed|error|warnings)" test_results.txt | tail -5
else
    echo "Test execution may have encountered issues"
fi

echo ""
echo "Full results saved to: test_results.txt"
echo "Exit code: $EXIT_CODE"

exit $EXIT_CODE