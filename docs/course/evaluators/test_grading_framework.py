#!/usr/bin/env python3
"""
Test suite for the TRANS-QML Course Grading Framework
Validates that the grading system works correctly with example solutions.

Run with: pytest test_grading_framework.py -v
"""

import pytest
import json
import tempfile
import os
from pathlib import Path

# Import the grading framework
from grading_framework import (
    CodeAnalyzer,
    TestRunner,
    BestPracticesChecker,
    ExerciseGrader,
    GradingResult,
    GradingCriterion,
    generate_report
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_python_code():
    """Simple Python code for testing"""
    return '''
"""Module docstring"""
import numpy as np
from typing import List, Optional
from PySide6.QtCore import QObject, Signal, Property

class MyClass(QObject):
    """A sample class."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        """Initialize the class."""
        super().__init__(parent)
        self._value = 0

    @Property(int, notify=valueChanged)
    def value(self) -> int:
        """Get value property."""
        return self._value

    @value.setter
    def value(self, val: int) -> None:
        if val != self._value:
            self._value = val
            self.valueChanged.emit(val)

    def calculate(self, x: float, y: float) -> float:
        """Calculate sum with error handling."""
        try:
            result = x + y
            return result
        except Exception as e:
            return 0.0
'''


@pytest.fixture
def sample_qml_code():
    """Simple QML code for testing"""
    return '''
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 800
    height: 600
    title: "Test Window"

    property int counter: 0

    Button {
        text: "Click Me"
        onClicked: {
            counter++
            console.log("Clicked:", counter)
        }
    }
}
'''


@pytest.fixture
def bad_python_code():
    """Python code with issues for testing"""
    return '''
import os, sys, numpy
from typing import *

class badClassName:
    def BadMethodName(self, x):
        if x > 0:
            if x > 10:
                if x > 100:
                    for i in range(x):
                        for j in range(x):
                            print(i, j)
        return x * 2
'''


@pytest.fixture
def temp_python_file(sample_python_code):
    """Create a temporary Python file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(sample_python_code)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_qml_file(sample_qml_code):
    """Create a temporary QML file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.qml', delete=False) as f:
        f.write(sample_qml_code)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_bad_python_file(bad_python_code):
    """Create a temporary Python file with bad code"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(bad_python_code)
        f.flush()
        yield f.name
    os.unlink(f.name)


# =============================================================================
# CodeAnalyzer Tests
# =============================================================================

class TestCodeAnalyzer:
    """Tests for static code analysis"""

    def test_parse_valid_file(self, temp_python_file):
        """Test parsing a valid Python file"""
        tree = CodeAnalyzer.parse_file(temp_python_file)
        assert tree is not None

    def test_parse_invalid_file(self):
        """Test parsing invalid Python code"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def broken(:\n    pass")
            f.flush()
            tree = CodeAnalyzer.parse_file(f.name)
        os.unlink(f.name)
        assert tree is None

    def test_count_lines(self, temp_python_file):
        """Test line counting"""
        counts = CodeAnalyzer.count_lines(temp_python_file)
        assert 'total' in counts
        assert 'code' in counts
        assert 'blank' in counts
        assert 'comments' in counts
        assert counts['total'] > 0
        assert counts['code'] > 0

    def test_calculate_complexity(self, temp_python_file):
        """Test complexity calculation"""
        tree = CodeAnalyzer.parse_file(temp_python_file)
        complexity = CodeAnalyzer.calculate_complexity(tree)

        assert 'cyclomatic_complexity' in complexity
        assert 'functions' in complexity
        assert 'classes' in complexity
        assert complexity['cyclomatic_complexity'] >= 1
        assert len(complexity['classes']) >= 1
        assert len(complexity['functions']) >= 2  # __init__, calculate, value getter/setter

    def test_high_complexity_detection(self, temp_bad_python_file):
        """Test detection of high complexity code"""
        tree = CodeAnalyzer.parse_file(temp_bad_python_file)
        complexity = CodeAnalyzer.calculate_complexity(tree)

        # Bad code should have higher complexity due to nested loops/conditions
        assert complexity['cyclomatic_complexity'] > 3
        assert complexity['max_nesting_depth'] >= 2

    def test_naming_conventions(self, temp_python_file):
        """Test PEP 8 naming convention checking"""
        tree = CodeAnalyzer.parse_file(temp_python_file)
        issues = CodeAnalyzer.check_naming_conventions(tree)

        # Good code should have few issues
        assert len(issues) <= 1

    def test_naming_conventions_bad_code(self, temp_bad_python_file):
        """Test detection of naming convention violations"""
        tree = CodeAnalyzer.parse_file(temp_bad_python_file)
        issues = CodeAnalyzer.check_naming_conventions(tree)

        # Bad code has 'badClassName' and 'BadMethodName'
        assert len(issues) >= 2

    def test_find_patterns(self, temp_python_file):
        """Test pattern detection"""
        tree = CodeAnalyzer.parse_file(temp_python_file)
        patterns = CodeAnalyzer.find_patterns(tree, [
            'uses_signal',
            'uses_property',
            'uses_qobject',
            'uses_numpy',
            'has_docstrings',
            'has_type_hints',
            'uses_try_except'
        ])

        assert patterns['uses_signal'] is True
        assert patterns['uses_property'] is True
        assert patterns['uses_qobject'] is True
        assert patterns['uses_numpy'] is True
        assert patterns['has_docstrings'] is True
        assert patterns['has_type_hints'] is True
        assert patterns['uses_try_except'] is True


# =============================================================================
# TestRunner Tests
# =============================================================================

class TestTestRunner:
    """Tests for the test runner"""

    def test_import_valid_module(self, temp_python_file):
        """Test importing a valid Python module"""
        module = TestRunner.import_module(temp_python_file)
        assert module is not None
        assert hasattr(module, 'MyClass')

    def test_run_tests_class_exists(self, temp_python_file):
        """Test checking if a class exists"""
        module = TestRunner.import_module(temp_python_file)
        tests = [
            {
                'name': 'class_exists',
                'type': 'class_exists',
                'target': 'MyClass'
            }
        ]
        results = TestRunner.run_tests(module, tests)

        assert len(results) == 1
        assert results[0]['passed'] is True

    def test_run_tests_class_not_exists(self, temp_python_file):
        """Test checking for non-existent class"""
        module = TestRunner.import_module(temp_python_file)
        tests = [
            {
                'name': 'missing_class',
                'type': 'class_exists',
                'target': 'NonExistentClass'
            }
        ]
        results = TestRunner.run_tests(module, tests)

        assert len(results) == 1
        assert results[0]['passed'] is False

    def test_run_tests_has_method(self, temp_python_file):
        """Test checking if class has a method"""
        module = TestRunner.import_module(temp_python_file)
        tests = [
            {
                'name': 'has_calculate',
                'type': 'has_method',
                'target': 'MyClass',
                'method': 'calculate'
            }
        ]
        results = TestRunner.run_tests(module, tests)

        assert len(results) == 1
        assert results[0]['passed'] is True

    def test_qml_syntax_valid(self, temp_qml_file):
        """Test QML syntax validation on valid file"""
        result = TestRunner.check_qml_syntax(temp_qml_file)

        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_qml_syntax_invalid(self):
        """Test QML syntax validation on invalid file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qml', delete=False) as f:
            f.write("Item { broken syntax {{{ }")
            f.flush()
            result = TestRunner.check_qml_syntax(f.name)
        os.unlink(f.name)

        assert result['valid'] is False


# =============================================================================
# BestPracticesChecker Tests
# =============================================================================

class TestBestPracticesChecker:
    """Tests for best practices checking"""

    def test_check_all_good_code(self, temp_python_file):
        """Test best practices on good code"""
        tree = CodeAnalyzer.parse_file(temp_python_file)
        criteria = BestPracticesChecker.check_all(temp_python_file, tree)

        assert len(criteria) > 0
        # Good code should pass most criteria
        passed = sum(1 for c in criteria if c.passed)
        assert passed >= len(criteria) // 2

    def test_check_all_bad_code(self, temp_bad_python_file):
        """Test best practices on bad code"""
        tree = CodeAnalyzer.parse_file(temp_bad_python_file)
        criteria = BestPracticesChecker.check_all(temp_bad_python_file, tree)

        assert len(criteria) > 0
        # Bad code should fail more criteria
        failed = sum(1 for c in criteria if not c.passed)
        assert failed >= 2


# =============================================================================
# ExerciseGrader Tests
# =============================================================================

class TestExerciseGrader:
    """Tests for the main grading system"""

    def test_grade_python_file(self, temp_python_file):
        """Test grading a Python file"""
        config = {
            'id': 'test_01',
            'required_patterns': ['QObject', 'Signal', 'Property'],
            'test_cases': [
                {
                    'name': 'class_exists',
                    'type': 'class_exists',
                    'target': 'MyClass'
                }
            ]
        }

        grader = ExerciseGrader(config)
        result = grader.grade(temp_python_file, 'test_student')

        assert isinstance(result, GradingResult)
        assert result.exercise_id == 'test_01'
        assert result.student_id == 'test_student'
        assert result.total_score > 0
        assert result.grade_letter in ['A', 'B', 'C', 'D', 'F']
        assert len(result.errors) == 0

    def test_grade_qml_file(self, temp_qml_file):
        """Test grading a QML file"""
        config = {
            'id': 'test_qml_01',
            'required_qml_patterns': [
                'import QtQuick',
                'ApplicationWindow',
                'visible: true'
            ]
        }

        grader = ExerciseGrader(config)
        result = grader.grade(temp_qml_file, 'test_student')

        assert isinstance(result, GradingResult)
        assert result.total_score > 0
        assert len(result.criteria) > 0

    def test_grade_missing_file(self):
        """Test grading a non-existent file"""
        config = {'id': 'test_missing'}
        grader = ExerciseGrader(config)
        result = grader.grade('/nonexistent/path.py', 'test_student')

        assert len(result.errors) > 0
        assert result.total_score == 0

    def test_grade_letter_assignment(self, temp_python_file):
        """Test that grade letters are assigned correctly"""
        config = {
            'id': 'test_grades',
            'required_patterns': ['QObject'],
            'test_cases': []
        }

        grader = ExerciseGrader(config)
        result = grader.grade(temp_python_file, 'test_student')

        # Grade should be assigned based on score
        assert result.grade_letter in ['A', 'B', 'C', 'D', 'F']
        if result.total_score / result.max_score >= 0.9:
            assert result.grade_letter == 'A'
        elif result.total_score / result.max_score >= 0.8:
            assert result.grade_letter == 'B'


# =============================================================================
# Report Generation Tests
# =============================================================================

class TestReportGeneration:
    """Tests for report generation"""

    def test_generate_text_report(self, temp_python_file):
        """Test generating a text report"""
        config = {'id': 'test_report'}
        grader = ExerciseGrader(config)
        result = grader.grade(temp_python_file, 'test_student')

        report = generate_report(result, 'text')

        assert 'GRADING REPORT' in report
        assert 'FINAL GRADE' in report
        assert result.grade_letter in report

    def test_generate_json_report(self, temp_python_file):
        """Test generating a JSON report"""
        config = {'id': 'test_json_report'}
        grader = ExerciseGrader(config)
        result = grader.grade(temp_python_file, 'test_student')

        report = generate_report(result, 'json')

        # Should be valid JSON
        data = json.loads(report)
        assert data['exercise_id'] == 'test_json_report'
        assert data['student_id'] == 'test_student'
        assert 'total_score' in data
        assert 'criteria' in data


# =============================================================================
# Integration Tests with Real Solutions
# =============================================================================

class TestRealSolutions:
    """Integration tests using actual course solutions"""

    @pytest.fixture
    def solutions_dir(self):
        """Get the solutions directory"""
        return Path(__file__).parent.parent / 'solutions'

    def test_grade_module01_solution_01(self, solutions_dir):
        """Test grading Module 1 Exercise 1 solution"""
        solution_file = solutions_dir / 'module01' / 'ex01_01_main.py'
        if not solution_file.exists():
            pytest.skip("Solution file not found")

        config = {
            'id': '01_01',
            'required_patterns': [
                'QApplication',
                'QQmlApplicationEngine',
                'engine.load'
            ],
            'test_cases': [
                {
                    'name': 'main_exists',
                    'type': 'function_call',
                    'target': 'main'
                }
            ]
        }

        grader = ExerciseGrader(config)
        result = grader.grade(str(solution_file), 'solution')

        # Solution should pass
        assert result.grade_letter in ['A', 'B']
        assert len(result.errors) == 0

    def test_grade_module01_solution_03(self, solutions_dir):
        """Test grading Module 1 Exercise 3 solution"""
        solution_file = solutions_dir / 'module01' / 'ex01_03_backend.py'
        if not solution_file.exists():
            pytest.skip("Solution file not found")

        config = {
            'id': '01_03',
            'required_patterns': [
                'QObject',
                'Signal',
                'Property',
                'statusChanged'
            ],
            'test_cases': [
                {
                    'name': 'class_exists',
                    'type': 'class_exists',
                    'target': 'AppBackend'
                },
                {
                    'name': 'has_status',
                    'type': 'has_method',
                    'target': 'AppBackend',
                    'method': 'status'
                }
            ]
        }

        grader = ExerciseGrader(config)
        result = grader.grade(str(solution_file), 'solution')

        # Solution should pass
        assert result.grade_letter in ['A', 'B']
        print(generate_report(result, 'text'))

    def test_grade_module01_qml_solution(self, solutions_dir):
        """Test grading Module 1 QML solution"""
        solution_file = solutions_dir / 'module01' / 'ex01_01_Main.qml'
        if not solution_file.exists():
            pytest.skip("QML solution file not found")

        config = {
            'id': '01_01_qml',
            'required_qml_patterns': [
                'import QtQuick',
                'ApplicationWindow',
                'visible: true',
                'title:'
            ]
        }

        grader = ExerciseGrader(config)
        result = grader.grade(str(solution_file), 'solution')

        # Solution should pass
        assert result.total_score > 0
        print(generate_report(result, 'text'))


# =============================================================================
# GradingCriterion Tests
# =============================================================================

class TestGradingCriterion:
    """Tests for the GradingCriterion dataclass"""

    def test_criterion_creation(self):
        """Test creating a grading criterion"""
        criterion = GradingCriterion(
            name='test_criterion',
            description='A test criterion',
            weight=0.5,
            max_points=10,
            earned_points=8,
            passed=True,
            feedback='Good job!'
        )

        assert criterion.name == 'test_criterion'
        assert criterion.weight == 0.5
        assert criterion.passed is True
        assert criterion.earned_points == 8

    def test_criterion_defaults(self):
        """Test criterion default values"""
        criterion = GradingCriterion(
            name='minimal',
            description='Minimal criterion',
            weight=1.0,
            max_points=100
        )

        assert criterion.earned_points == 0.0
        assert criterion.passed is False
        assert criterion.feedback == ""
        assert criterion.details == []


# =============================================================================
# Main Test Runner
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
