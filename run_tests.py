#!/usr/bin/env python3
"""
TRANS-QML Test Runner Script
Automates running tests with coverage reporting

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --quick      # Run quick tests only (skip slow)
    python run_tests.py --coverage   # Run with coverage report
    python run_tests.py --module models    # Run specific module tests
    python run_tests.py --verbose    # Verbose output
    python run_tests.py --html       # Generate HTML coverage report
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd, verbose=False):
    """Run a command and return success status."""
    if verbose:
        print(f"\n{'='*60}")
        print(f"Running: {' '.join(cmd)}")
        print('='*60)

    result = subprocess.run(cmd, capture_output=not verbose)

    if not verbose and result.returncode != 0:
        print(result.stdout.decode())
        print(result.stderr.decode())

    return result.returncode == 0


def check_dependencies():
    """Check if required test dependencies are installed."""
    missing = []

    try:
        import pytest
    except ImportError:
        missing.append('pytest')

    try:
        import pytest_cov
    except ImportError:
        missing.append('pytest-cov')

    if missing:
        print("Missing test dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall with: pip install pytest pytest-cov")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description='TRANS-QML Test Runner')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Run quick tests only (skip slow)')
    parser.add_argument('--coverage', '-c', action='store_true',
                        help='Run with coverage report')
    parser.add_argument('--html', action='store_true',
                        help='Generate HTML coverage report')
    parser.add_argument('--module', '-m', type=str,
                        choices=['models', 'backend', 'loaders', 'processing', 'integration', 'all'],
                        default='all',
                        help='Run tests for specific module')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--failfast', '-x', action='store_true',
                        help='Stop on first failure')
    parser.add_argument('--parallel', '-p', action='store_true',
                        help='Run tests in parallel (requires pytest-xdist)')
    parser.add_argument('--markers', action='store_true',
                        help='Show available test markers')

    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Get project root
    project_root = Path(__file__).parent
    tests_dir = project_root / 'tests'

    if not tests_dir.exists():
        print(f"Error: Tests directory not found at {tests_dir}")
        sys.exit(1)

    # Build pytest command
    cmd = ['python', '-m', 'pytest']

    # Add test path based on module
    if args.module == 'all':
        cmd.append(str(tests_dir))
    elif args.module == 'models':
        cmd.append(str(tests_dir / 'test_models'))
    elif args.module == 'backend':
        cmd.append(str(tests_dir / 'test_backend'))
    elif args.module == 'loaders':
        cmd.append(str(tests_dir / 'test_data_loaders'))
    elif args.module == 'processing':
        cmd.append(str(tests_dir / 'test_processing'))
    elif args.module == 'integration':
        cmd.append(str(tests_dir / 'test_integration'))

    # Add options
    if args.verbose:
        cmd.append('-v')

    if args.quick:
        cmd.extend(['-m', 'not slow'])

    if args.failfast:
        cmd.append('-x')

    if args.parallel:
        cmd.extend(['-n', 'auto'])

    if args.markers:
        cmd.append('--markers')

    # Coverage options
    if args.coverage or args.html:
        cmd.extend([
            '--cov=src',
            '--cov-report=term-missing',
        ])

        if args.html:
            cmd.append('--cov-report=html')

    # Run tests
    print("\n" + "="*60)
    print("TRANS-QML Test Suite")
    print("="*60)
    print(f"\nTest directory: {tests_dir}")
    print(f"Module: {args.module}")
    print(f"Quick mode: {args.quick}")
    print(f"Coverage: {args.coverage or args.html}")
    print()

    success = run_command(cmd, verbose=True)

    if args.html and success:
        html_report = project_root / 'htmlcov' / 'index.html'
        print(f"\n{'='*60}")
        print(f"HTML coverage report: {html_report}")
        print("="*60)

    # Print summary
    print("\n" + "="*60)
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("="*60)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
