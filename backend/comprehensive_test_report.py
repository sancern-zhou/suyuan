#!/usr/bin/env python
"""
Comprehensive Test Report Generator
Analyzes test files and provides detailed reporting
"""
import os
import re
from pathlib import Path
from collections import defaultdict

def generate_test_report():
    """Generate comprehensive test report"""
    test_dir = Path("/home/xckj/suyuan/backend/tests")

    print("=" * 80)
    print("COMPREHENSIVE TEST REPORT FOR ATMOSPHERIC ENVIRONMENT ANALYSIS PLATFORM")
    print("=" * 80)
    print(f"Project Location: /home/xckj/suyuan/backend")
    print(f"Test Directory: {test_dir}")
    print(f"Report Generated: 2026-05-19")
    print()

    # Test file analysis
    test_files = list(test_dir.rglob("test_*.py"))
    print(f"✓ Total Test Files: {len(test_files)}")

    # Categorize tests
    categories = {
        'Agent Tests': [],
        'Tool Tests': [],
        'API Tests': [],
        'Integration Tests': [],
        'Office Tests': [],
        'Chart Tests': [],
        'Data Tests': [],
        'Other Tests': []
    }

    for test_file in test_files:
        filename = test_file.name
        if 'agent' in filename.lower() or 'react' in filename.lower():
            categories['Agent Tests'].append(filename)
        elif 'tool' in filename.lower():
            categories['Tool Tests'].append(filename)
        elif 'api' in filename.lower() or 'gd_suncere' in filename.lower():
            categories['API Tests'].append(filename)
        elif 'integration' in filename.lower() or 'e2e' in filename.lower():
            categories['Integration Tests'].append(filename)
        elif 'office' in filename.lower() or 'word' in filename.lower() or 'excel' in filename.lower():
            categories['Office Tests'].append(filename)
        elif 'chart' in filename.lower() or 'visualization' in filename.lower():
            categories['Chart Tests'].append(filename)
        elif 'data' in filename.lower() or 'query' in filename.lower():
            categories['Data Tests'].append(filename)
        else:
            categories['Other Tests'].append(filename)

    print("\n" + "=" * 80)
    print("TEST CATEGORIES")
    print("=" * 80)

    for category, files in categories.items():
        if files:
            print(f"\n{category} ({len(files)} files):")
            for file in sorted(files)[:5]:  # Show first 5
                print(f"  - {file}")
            if len(files) > 5:
                print(f"  ... and {len(files) - 5} more")

    # Test function analysis
    print("\n" + "=" * 80)
    print("TEST FUNCTION ANALYSIS (Sample of 20 files)")
    print("=" * 80)

    total_functions = 0
    async_functions = 0
    test_patterns = defaultdict(int)

    for test_file in test_files[:20]:  # Sample first 20
        try:
            content = test_file.read_text(encoding='utf-8', errors='ignore')
            functions = re.findall(r'def (test_\w+)', content)
            total_functions += len(functions)

            async_funcs = re.findall(r'async def (test_\w+)', content)
            async_functions += len(async_funcs)

            for func in functions:
                if 'bash' in func:
                    test_patterns['bash'] += 1
                elif 'office' in func:
                    test_patterns['office'] += 1
                elif 'chart' in func:
                    test_patterns['chart'] += 1
                elif 'api' in func:
                    test_patterns['api'] += 1
                else:
                    test_patterns['other'] += 1

        except Exception as e:
            print(f"Error analyzing {test_file.name}: {e}")

    print(f"✓ Total test functions found: {total_functions}")
    print(f"✓ Async test functions: {async_functions}")
    print("\nTest patterns:")
    for pattern, count in sorted(test_patterns.items()):
        print(f"  - {pattern}: {count}")

    # Environment check
    print("\n" + "=" * 80)
    print("ENVIRONMENT CHECK")
    print("=" * 80)

    dependencies = {
        'pytest': 'pytest',
        'pytest-asyncio': 'pytest_asyncio',
        'fastapi': 'fastapi',
        'anthropic': 'anthropic',
        'openai': 'openai',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib'
    }

    available_deps = []
    missing_deps = []

    for name, module in dependencies.items():
        try:
            __import__(module)
            available_deps.append(name)
            print(f"✓ {name:20} - Available")
        except ImportError:
            missing_deps.append(name)
            print(f"✗ {name:20} - Missing")

    # Code quality tools check
    print("\n" + "=" * 80)
    print("CODE QUALITY TOOLS")
    print("=" * 80)

    quality_tools = ['ruff', 'flake8', 'mypy', 'black', 'pylint', 'isort']
    available_quality = []

    for tool in quality_tools:
        try:
            __import__(tool)
            available_quality.append(tool)
            print(f"✓ {tool:10} - Available")
        except ImportError:
            print(f"✗ {tool:10} - Not available")

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    if not missing_deps:
        print("✓ All core dependencies are available")
        print("  → Tests should run successfully")
        print("  → Command: python -m pytest tests/ -v --tb=short")
    else:
        print(f"✗ Missing dependencies: {', '.join(missing_deps)}")
        print("  → Install missing dependencies: pip install -r requirements.txt")

    if available_quality:
        print(f"\n✓ Available code quality tools: {', '.join(available_quality)}")
        print("  → Run code quality checks:")
        for tool in available_quality:
            if tool == 'ruff':
                print("    - ruff check .")
            elif tool == 'black':
                print("    - black --check .")
            elif tool == 'mypy':
                print("    - mypy app/")
            elif tool == 'flake8':
                print("    - flake8 app/")
    else:
        print("\n✗ No code quality tools available")
        print("  → Consider installing: ruff, black, mypy")

    # Test execution summary
    print("\n" + "=" * 80)
    print("TEST EXECUTION SUMMARY")
    print("=" * 80)

    print(f"""
Based on the analysis of {len(test_files)} test files:

PROJECT STRUCTURE:
- Location: /home/xckj/suyuan/backend
- Framework: FastAPI + Vue 3
- Test Framework: pytest + pytest-asyncio
- Test Files: {len(test_files)} total

TEST COVERAGE AREAS:
- Agent System: {len(categories['Agent Tests'])} files
- Tool Testing: {len(categories['Tool Tests'])} files
- API Integration: {len(categories['API Tests'])} files
- Integration Tests: {len(categories['Integration Tests'])} files
- Office Tools: {len(categories['Office Tests'])} files
- Chart Generation: {len(categories['Chart Tests'])} files
- Data Processing: {len(categories['Data Tests'])} files

DEPENDENCY STATUS:
- Available: {len(available_deps)}/{len(dependencies)}
- Code Quality Tools: {len(available_quality)}/{len(quality_tools)}

RECOMMENDED COMMANDS:
1. Run all tests:        python -m pytest tests/ -v --tb=short
2. Run specific tests:   python -m pytest tests/test_bash_tool.py -v
3. Run with coverage:    python -m pytest tests/ --cov=app --cov-report=html
4. Run fast tests only:  python -m pytest tests/ -m "not slow"
5. Run quality checks:   {'Available' if available_quality else 'Install tools first'}

NOTE: Full test execution requires all dependencies to be installed.
""")

    return {
        'total_tests': len(test_files),
        'dependencies_ok': len(missing_deps) == 0,
        'quality_tools_available': len(available_quality),
        'categories': {k: len(v) for k, v in categories.items()}
    }

if __name__ == "__main__":
    generate_test_report()