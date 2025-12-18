#!/bin/bash
#
# TRANS-QML Test Runner
# Installs dependencies and runs tests
#
# Usage:
#   ./test.sh              # Run all tests
#   ./test.sh --coverage   # Run with coverage report
#   ./test.sh --html       # Generate HTML coverage report
#   ./test.sh --quick      # Skip slow tests
#   ./test.sh --install    # Only install dependencies
#   ./test.sh --help       # Show help
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory (project root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Print colored message
print_msg() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Show help
show_help() {
    echo "TRANS-QML Test Runner"
    echo ""
    echo "Usage: ./test.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --coverage, -c    Run tests with coverage report"
    echo "  --html            Generate HTML coverage report (opens in browser)"
    echo "  --quick, -q       Skip slow tests"
    echo "  --verbose, -v     Verbose output"
    echo "  --install, -i     Only install dependencies (don't run tests)"
    echo "  --no-install      Skip dependency installation"
    echo "  --module MODULE   Run specific module (models, backend, loaders, integration)"
    echo "  --failfast, -x    Stop on first failure"
    echo "  --help, -h        Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./test.sh                      # Run all tests"
    echo "  ./test.sh --coverage           # Run with coverage"
    echo "  ./test.sh --module backend     # Run backend tests only"
    echo "  ./test.sh --quick --verbose    # Quick tests with verbose output"
    echo ""
}

# Check Python version
check_python() {
    print_msg "Checking Python version..."

    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python not found. Please install Python 3.8+"
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    print_success "Found Python $PYTHON_VERSION"
}

# Install dependencies
install_deps() {
    print_msg "Installing dependencies..."

    # Upgrade pip
    $PYTHON_CMD -m pip install --upgrade pip -q

    # Install main requirements
    if [ -f "requirements.txt" ]; then
        print_msg "Installing from requirements.txt..."
        $PYTHON_CMD -m pip install -r requirements.txt -q
        print_success "Main dependencies installed"
    else
        print_warning "requirements.txt not found"
    fi

    # Install test dependencies
    print_msg "Installing test dependencies..."
    $PYTHON_CMD -m pip install pytest pytest-cov -q
    print_success "Test dependencies installed"
}

# Check if dependencies are installed
check_deps() {
    $PYTHON_CMD -c "import pytest" 2>/dev/null
    return $?
}

# Run tests
run_tests() {
    local PYTEST_ARGS=("tests/")

    # Add module path if specified
    if [ -n "$MODULE" ]; then
        case $MODULE in
            models)
                PYTEST_ARGS=("tests/test_models/")
                ;;
            backend)
                PYTEST_ARGS=("tests/test_backend/")
                ;;
            loaders)
                PYTEST_ARGS=("tests/test_data_loaders/")
                ;;
            integration)
                PYTEST_ARGS=("tests/test_integration/")
                ;;
            *)
                print_error "Unknown module: $MODULE"
                exit 1
                ;;
        esac
    fi

    # Add options
    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS+=("-v")
    fi

    if [ "$QUICK" = true ]; then
        PYTEST_ARGS+=("-m" "not slow")
    fi

    if [ "$FAILFAST" = true ]; then
        PYTEST_ARGS+=("-x")
    fi

    if [ "$COVERAGE" = true ] || [ "$HTML_REPORT" = true ]; then
        PYTEST_ARGS+=("--cov=src" "--cov-report=term-missing")
    fi

    if [ "$HTML_REPORT" = true ]; then
        PYTEST_ARGS+=("--cov-report=html")
    fi

    print_msg "Running tests..."
    echo ""

    $PYTHON_CMD -m pytest "${PYTEST_ARGS[@]}"
    TEST_RESULT=$?

    return $TEST_RESULT
}

# Open HTML report
open_html_report() {
    local REPORT_PATH="$SCRIPT_DIR/htmlcov/index.html"

    if [ -f "$REPORT_PATH" ]; then
        print_msg "Opening coverage report..."

        # Detect OS and open browser
        case "$(uname -s)" in
            Darwin)
                open "$REPORT_PATH"
                ;;
            Linux)
                xdg-open "$REPORT_PATH" 2>/dev/null || print_warning "Could not open browser. Report at: $REPORT_PATH"
                ;;
            *)
                print_warning "Report generated at: $REPORT_PATH"
                ;;
        esac
    fi
}

# Parse arguments
COVERAGE=false
HTML_REPORT=false
QUICK=false
VERBOSE=false
INSTALL_ONLY=false
NO_INSTALL=false
FAILFAST=false
MODULE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --html)
            HTML_REPORT=true
            COVERAGE=true
            shift
            ;;
        --quick|-q)
            QUICK=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --install|-i)
            INSTALL_ONLY=true
            shift
            ;;
        --no-install)
            NO_INSTALL=true
            shift
            ;;
        --failfast|-x)
            FAILFAST=true
            shift
            ;;
        --module)
            MODULE="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main execution
echo ""
echo "========================================"
echo "     TRANS-QML Test Suite"
echo "========================================"
echo ""

check_python

# Install dependencies if needed
if [ "$NO_INSTALL" = false ]; then
    if [ "$INSTALL_ONLY" = true ] || ! check_deps; then
        install_deps
    else
        print_success "Dependencies already installed"
    fi
fi

if [ "$INSTALL_ONLY" = true ]; then
    echo ""
    print_success "Dependencies installed. Run ./test.sh to run tests."
    exit 0
fi

echo ""
echo "----------------------------------------"
echo "Test Configuration:"
echo "  Module:    ${MODULE:-all}"
echo "  Coverage:  $COVERAGE"
echo "  Quick:     $QUICK"
echo "  Verbose:   $VERBOSE"
echo "----------------------------------------"
echo ""

# Run tests
if run_tests; then
    echo ""
    echo "========================================"
    print_success "All tests passed!"
    echo "========================================"

    if [ "$HTML_REPORT" = true ]; then
        open_html_report
    fi

    exit 0
else
    echo ""
    echo "========================================"
    print_error "Some tests failed"
    echo "========================================"
    exit 1
fi
