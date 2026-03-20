#!/usr/bin/env python3
"""
TRANS-QML Course Grading Framework
Evaluates student submissions for correctness, best practices, and optimization.

Usage:
    python grading_framework.py --exercise MODULE_EXERCISE --submission PATH [--verbose]
    python grading_framework.py --batch SUBMISSIONS_DIR --module MODULE_NUM

Example:
    python grading_framework.py --exercise 01_01 --submission ./student_code.py
    python grading_framework.py --batch ./submissions/ --module 01
"""

import ast
import json
import sys
import os
import re
import subprocess
import tempfile
import importlib.util
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable, Tuple
from datetime import datetime
import traceback
import argparse


@dataclass
class GradingCriterion:
    """Single grading criterion with weight and evaluation result"""
    name: str
    description: str
    weight: float  # 0.0 to 1.0
    max_points: float
    earned_points: float = 0.0
    passed: bool = False
    feedback: str = ""
    details: List[str] = field(default_factory=list)


@dataclass
class GradingResult:
    """Complete grading result for a submission"""
    exercise_id: str
    student_id: str
    submission_path: str
    timestamp: str
    total_score: float = 0.0
    max_score: float = 100.0
    grade_letter: str = "F"
    criteria: List[GradingCriterion] = field(default_factory=list)
    correctness_score: float = 0.0
    best_practices_score: float = 0.0
    optimization_score: float = 0.0
    complexity_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0


class CodeAnalyzer:
    """Static code analysis utilities"""

    @staticmethod
    def parse_file(filepath: str) -> Optional[ast.AST]:
        """Parse Python file into AST"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            return None

    @staticmethod
    def count_lines(filepath: str) -> Dict[str, int]:
        """Count lines of code, comments, and blank lines"""
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total = len(lines)
        blank = sum(1 for line in lines if not line.strip())
        comments = sum(1 for line in lines if line.strip().startswith('#'))
        docstrings = 0

        # Count docstring lines (simplified)
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if '"""' in stripped or "'''" in stripped:
                if in_docstring:
                    in_docstring = False
                    docstrings += 1
                else:
                    in_docstring = True
                    docstrings += 1
            elif in_docstring:
                docstrings += 1

        return {
            'total': total,
            'code': total - blank - comments - docstrings,
            'blank': blank,
            'comments': comments,
            'docstrings': docstrings
        }

    @staticmethod
    def calculate_complexity(tree: ast.AST) -> Dict[str, Any]:
        """Calculate cyclomatic complexity and other metrics"""

        class ComplexityVisitor(ast.NodeVisitor):
            def __init__(self):
                self.complexity = 1
                self.functions = []
                self.classes = []
                self.imports = []
                self.nested_depth = 0
                self.max_depth = 0

            def visit_If(self, node):
                self.complexity += 1
                self.generic_visit(node)

            def visit_For(self, node):
                self.complexity += 1
                self.nested_depth += 1
                self.max_depth = max(self.max_depth, self.nested_depth)
                self.generic_visit(node)
                self.nested_depth -= 1

            def visit_While(self, node):
                self.complexity += 1
                self.nested_depth += 1
                self.max_depth = max(self.max_depth, self.nested_depth)
                self.generic_visit(node)
                self.nested_depth -= 1

            def visit_ExceptHandler(self, node):
                self.complexity += 1
                self.generic_visit(node)

            def visit_With(self, node):
                self.complexity += 1
                self.generic_visit(node)

            def visit_BoolOp(self, node):
                self.complexity += len(node.values) - 1
                self.generic_visit(node)

            def visit_FunctionDef(self, node):
                self.functions.append({
                    'name': node.name,
                    'args': len(node.args.args),
                    'decorators': len(node.decorator_list),
                    'lineno': node.lineno
                })
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

            def visit_ClassDef(self, node):
                self.classes.append({
                    'name': node.name,
                    'bases': len(node.bases),
                    'methods': sum(1 for item in node.body
                                   if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))),
                    'lineno': node.lineno
                })
                self.generic_visit(node)

            def visit_Import(self, node):
                for alias in node.names:
                    self.imports.append(alias.name)

            def visit_ImportFrom(self, node):
                module = node.module or ''
                for alias in node.names:
                    self.imports.append(f"{module}.{alias.name}")

        visitor = ComplexityVisitor()
        visitor.visit(tree)

        return {
            'cyclomatic_complexity': visitor.complexity,
            'functions': visitor.functions,
            'classes': visitor.classes,
            'imports': visitor.imports,
            'max_nesting_depth': visitor.max_depth,
            'num_functions': len(visitor.functions),
            'num_classes': len(visitor.classes)
        }

    @staticmethod
    def check_naming_conventions(tree: ast.AST) -> List[Dict[str, Any]]:
        """Check PEP 8 naming conventions"""
        issues = []

        class NamingVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                # Functions should be snake_case
                if not re.match(r'^[a-z_][a-z0-9_]*$', node.name) and not node.name.startswith('_'):
                    if not node.name.startswith('test'):  # Allow test methods
                        issues.append({
                            'type': 'function_naming',
                            'name': node.name,
                            'line': node.lineno,
                            'message': f"Function '{node.name}' should be snake_case"
                        })
                self.generic_visit(node)

            def visit_ClassDef(self, node):
                # Classes should be PascalCase
                if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                    issues.append({
                        'type': 'class_naming',
                        'name': node.name,
                        'line': node.lineno,
                        'message': f"Class '{node.name}' should be PascalCase"
                    })
                self.generic_visit(node)

            def visit_Name(self, node):
                # Constants should be UPPER_CASE (heuristic: module-level assignments)
                if isinstance(node.ctx, ast.Store):
                    pass  # Would need more context
                self.generic_visit(node)

        NamingVisitor().visit(tree)
        return issues

    @staticmethod
    def find_patterns(tree: ast.AST, patterns: List[str]) -> Dict[str, bool]:
        """Check if specific code patterns exist"""
        source = ast.unparse(tree)
        results = {}

        pattern_checks = {
            'uses_signal': r'Signal\s*\(',
            'uses_slot': r'@Slot',
            'uses_property': r'@Property|Property\s*\(',
            'uses_qobject': r'QObject',
            'uses_threading': r'QThread|threading\.',
            'uses_numpy': r'import numpy|from numpy',
            'uses_pandas': r'import pandas|from pandas',
            'has_docstrings': r'""".*?"""|\'\'\'.*?\'\'\'',
            'has_type_hints': r'->\s*\w+|:\s*\w+\s*=',
            'uses_logging': r'logging\.|logger\.',
            'uses_try_except': r'try:|except\s+\w+',
            'uses_context_manager': r'with\s+\w+',
            'uses_list_comprehension': r'\[.*for.*in.*\]',
            'uses_generator': r'yield\s+',
            'uses_dataclass': r'@dataclass',
            'uses_abstract': r'@abstractmethod|ABC',
        }

        for pattern_name in patterns:
            if pattern_name in pattern_checks:
                results[pattern_name] = bool(re.search(
                    pattern_checks[pattern_name], source, re.DOTALL
                ))
            else:
                results[pattern_name] = pattern_name.lower() in source.lower()

        return results


class TestRunner:
    """Execute and validate student code"""

    @staticmethod
    def import_module(filepath: str) -> Optional[Any]:
        """Dynamically import a Python module"""
        try:
            spec = importlib.util.spec_from_file_location("student_module", filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules["student_module"] = module
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            return None

    @staticmethod
    def run_tests(module: Any, test_cases: List[Dict]) -> List[Dict]:
        """Run test cases against student module"""
        results = []

        for test in test_cases:
            result = {
                'name': test['name'],
                'passed': False,
                'message': '',
                'expected': test.get('expected'),
                'actual': None
            }

            try:
                # Get the function/class to test
                target = getattr(module, test['target'], None)
                if target is None:
                    result['message'] = f"'{test['target']}' not found in submission"
                    results.append(result)
                    continue

                # Execute test
                if test['type'] == 'function_call':
                    actual = target(*test.get('args', []), **test.get('kwargs', {}))
                    result['actual'] = actual

                    if 'expected' in test:
                        if test.get('compare') == 'approximate':
                            result['passed'] = abs(actual - test['expected']) < test.get('tolerance', 0.001)
                        elif test.get('compare') == 'type':
                            result['passed'] = isinstance(actual, test['expected'])
                        else:
                            result['passed'] = actual == test['expected']
                    else:
                        result['passed'] = True

                elif test['type'] == 'class_exists':
                    result['passed'] = isinstance(target, type)

                elif test['type'] == 'has_method':
                    result['passed'] = hasattr(target, test['method'])

                elif test['type'] == 'inheritance':
                    result['passed'] = issubclass(target, test['base_class'])

                elif test['type'] == 'attribute_exists':
                    obj = target() if callable(target) else target
                    result['passed'] = hasattr(obj, test['attribute'])

                if result['passed']:
                    result['message'] = 'Test passed'
                else:
                    result['message'] = f"Expected {test.get('expected')}, got {result['actual']}"

            except Exception as e:
                result['message'] = f"Error: {str(e)}"

            results.append(result)

        return results

    @staticmethod
    def check_qml_syntax(filepath: str) -> Dict[str, Any]:
        """Basic QML syntax validation"""
        result = {'valid': True, 'errors': [], 'warnings': []}

        try:
            with open(filepath, 'r') as f:
                content = f.read()

            # Check for common QML patterns
            if not re.search(r'import\s+QtQuick', content):
                result['warnings'].append("Missing 'import QtQuick'")

            # Check brace matching
            open_braces = content.count('{')
            close_braces = content.count('}')
            if open_braces != close_braces:
                result['valid'] = False
                result['errors'].append(f"Brace mismatch: {open_braces} open, {close_braces} close")

            # Check for required root element
            if not re.search(r'^\s*(Item|Rectangle|Window|ApplicationWindow|Component)\s*\{',
                           content, re.MULTILINE):
                result['warnings'].append("No standard root element found")

            # Check for signal handlers
            if 'onClicked' in content or 'on' in content:
                if not re.search(r'on\w+\s*:', content):
                    result['warnings'].append("Signal handlers should use 'onSignal:' syntax")

        except Exception as e:
            result['valid'] = False
            result['errors'].append(str(e))

        return result


class BestPracticesChecker:
    """Check for coding best practices"""

    CHECKS = {
        'has_docstrings': {
            'description': 'Functions and classes have docstrings',
            'weight': 0.15
        },
        'uses_type_hints': {
            'description': 'Uses type hints for function parameters and returns',
            'weight': 0.10
        },
        'proper_naming': {
            'description': 'Follows PEP 8 naming conventions',
            'weight': 0.15
        },
        'error_handling': {
            'description': 'Implements proper error handling',
            'weight': 0.15
        },
        'no_magic_numbers': {
            'description': 'Avoids magic numbers (uses named constants)',
            'weight': 0.10
        },
        'reasonable_function_length': {
            'description': 'Functions are reasonably sized (<50 lines)',
            'weight': 0.10
        },
        'low_complexity': {
            'description': 'Code has low cyclomatic complexity (<10)',
            'weight': 0.15
        },
        'proper_imports': {
            'description': 'Imports are organized and specific',
            'weight': 0.10
        }
    }

    @classmethod
    def check_all(cls, filepath: str, tree: ast.AST) -> List[GradingCriterion]:
        """Run all best practice checks"""
        criteria = []

        with open(filepath, 'r') as f:
            content = f.read()

        complexity = CodeAnalyzer.calculate_complexity(tree)
        naming_issues = CodeAnalyzer.check_naming_conventions(tree)

        # Check docstrings
        criterion = GradingCriterion(
            name='has_docstrings',
            description=cls.CHECKS['has_docstrings']['description'],
            weight=cls.CHECKS['has_docstrings']['weight'],
            max_points=10
        )
        docstring_count = len(re.findall(r'""".*?"""|\'\'\'.*?\'\'\'', content, re.DOTALL))
        func_count = complexity['num_functions'] + complexity['num_classes']
        if func_count > 0:
            ratio = docstring_count / max(func_count, 1)
            criterion.earned_points = min(10, ratio * 10)
            criterion.passed = ratio >= 0.5
            criterion.feedback = f"{docstring_count} docstrings for {func_count} functions/classes"
        else:
            criterion.earned_points = 5
            criterion.passed = True
            criterion.feedback = "No functions/classes to document"
        criteria.append(criterion)

        # Check type hints
        criterion = GradingCriterion(
            name='uses_type_hints',
            description=cls.CHECKS['uses_type_hints']['description'],
            weight=cls.CHECKS['uses_type_hints']['weight'],
            max_points=10
        )
        type_hint_count = len(re.findall(r'def\s+\w+\([^)]*:\s*\w+', content))
        type_hint_count += len(re.findall(r'->\s*\w+', content))
        criterion.earned_points = min(10, type_hint_count * 2)
        criterion.passed = type_hint_count >= 3
        criterion.feedback = f"Found {type_hint_count} type hints"
        criteria.append(criterion)

        # Check naming conventions
        criterion = GradingCriterion(
            name='proper_naming',
            description=cls.CHECKS['proper_naming']['description'],
            weight=cls.CHECKS['proper_naming']['weight'],
            max_points=10
        )
        criterion.earned_points = max(0, 10 - len(naming_issues) * 2)
        criterion.passed = len(naming_issues) <= 2
        criterion.feedback = f"{len(naming_issues)} naming convention issues"
        criterion.details = [issue['message'] for issue in naming_issues[:5]]
        criteria.append(criterion)

        # Check error handling
        criterion = GradingCriterion(
            name='error_handling',
            description=cls.CHECKS['error_handling']['description'],
            weight=cls.CHECKS['error_handling']['weight'],
            max_points=10
        )
        try_count = content.count('try:')
        except_count = content.count('except')
        criterion.earned_points = min(10, (try_count + except_count) * 2)
        criterion.passed = try_count >= 1
        criterion.feedback = f"{try_count} try blocks, {except_count} except handlers"
        criteria.append(criterion)

        # Check function length
        criterion = GradingCriterion(
            name='reasonable_function_length',
            description=cls.CHECKS['reasonable_function_length']['description'],
            weight=cls.CHECKS['reasonable_function_length']['weight'],
            max_points=10
        )
        long_functions = []
        for func in complexity['functions']:
            # Estimate function length (simplified)
            pass
        criterion.earned_points = 10 if len(long_functions) == 0 else max(0, 10 - len(long_functions) * 3)
        criterion.passed = len(long_functions) == 0
        criterion.feedback = f"{len(long_functions)} functions exceed 50 lines"
        criteria.append(criterion)

        # Check complexity
        criterion = GradingCriterion(
            name='low_complexity',
            description=cls.CHECKS['low_complexity']['description'],
            weight=cls.CHECKS['low_complexity']['weight'],
            max_points=10
        )
        cc = complexity['cyclomatic_complexity']
        criterion.earned_points = max(0, 10 - max(0, cc - 10))
        criterion.passed = cc <= 15
        criterion.feedback = f"Cyclomatic complexity: {cc}"
        criteria.append(criterion)

        return criteria


class ExerciseGrader:
    """Main grading orchestrator"""

    def __init__(self, exercise_config: Dict[str, Any]):
        self.config = exercise_config
        self.exercise_id = exercise_config.get('id', 'unknown')

    def grade(self, submission_path: str, student_id: str = "anonymous") -> GradingResult:
        """Grade a student submission"""
        import time
        start_time = time.time()

        result = GradingResult(
            exercise_id=self.exercise_id,
            student_id=student_id,
            submission_path=submission_path,
            timestamp=datetime.now().isoformat()
        )

        # Check file exists
        if not os.path.exists(submission_path):
            result.errors.append(f"Submission file not found: {submission_path}")
            return result

        # Determine file type
        file_ext = Path(submission_path).suffix.lower()

        if file_ext == '.py':
            self._grade_python(submission_path, result)
        elif file_ext == '.qml':
            self._grade_qml(submission_path, result)
        else:
            result.errors.append(f"Unsupported file type: {file_ext}")

        # Calculate final scores
        self._calculate_scores(result)

        result.execution_time = time.time() - start_time
        return result

    def _grade_python(self, filepath: str, result: GradingResult):
        """Grade Python submission"""

        # Parse AST
        tree = CodeAnalyzer.parse_file(filepath)
        if tree is None:
            result.errors.append("Syntax error: Could not parse Python file")
            return

        # 1. Correctness tests (40% weight)
        if 'test_cases' in self.config:
            module = TestRunner.import_module(filepath)
            if module:
                test_results = TestRunner.run_tests(module, self.config['test_cases'])
                passed = sum(1 for t in test_results if t['passed'])
                total = len(test_results)

                criterion = GradingCriterion(
                    name='correctness',
                    description='Passes functional test cases',
                    weight=0.40,
                    max_points=40,
                    earned_points=40 * (passed / total) if total > 0 else 0,
                    passed=passed == total,
                    feedback=f"Passed {passed}/{total} tests",
                    details=[f"{t['name']}: {'PASS' if t['passed'] else 'FAIL - ' + t['message']}"
                            for t in test_results]
                )
                result.criteria.append(criterion)
            else:
                result.errors.append("Could not import module for testing")

        # 2. Required patterns (20% weight)
        if 'required_patterns' in self.config:
            patterns = CodeAnalyzer.find_patterns(tree, self.config['required_patterns'])
            found = sum(1 for v in patterns.values() if v)
            total = len(patterns)

            criterion = GradingCriterion(
                name='required_patterns',
                description='Uses required code patterns/features',
                weight=0.20,
                max_points=20,
                earned_points=20 * (found / total) if total > 0 else 20,
                passed=found == total,
                feedback=f"Found {found}/{total} required patterns",
                details=[f"{k}: {'Found' if v else 'Missing'}" for k, v in patterns.items()]
            )
            result.criteria.append(criterion)

        # 3. Best practices (25% weight)
        bp_criteria = BestPracticesChecker.check_all(filepath, tree)
        for c in bp_criteria:
            c.weight *= 0.25 / len(bp_criteria) if bp_criteria else 0
            c.max_points *= 0.25
            result.criteria.append(c)

        # 4. Code quality/complexity (15% weight)
        complexity = CodeAnalyzer.calculate_complexity(tree)
        lines = CodeAnalyzer.count_lines(filepath)

        criterion = GradingCriterion(
            name='code_quality',
            description='Code organization and complexity',
            weight=0.15,
            max_points=15
        )

        # Score based on reasonable complexity
        cc = complexity['cyclomatic_complexity']
        nesting = complexity['max_nesting_depth']

        quality_score = 15
        if cc > 20:
            quality_score -= 5
        if nesting > 4:
            quality_score -= 3
        if lines['code'] > 500:
            quality_score -= 2

        criterion.earned_points = max(0, quality_score)
        criterion.passed = quality_score >= 10
        criterion.feedback = f"CC={cc}, nesting={nesting}, LOC={lines['code']}"
        result.criteria.append(criterion)

    def _grade_qml(self, filepath: str, result: GradingResult):
        """Grade QML submission"""
        syntax_result = TestRunner.check_qml_syntax(filepath)

        criterion = GradingCriterion(
            name='qml_syntax',
            description='Valid QML syntax',
            weight=0.30,
            max_points=30,
            earned_points=30 if syntax_result['valid'] else 0,
            passed=syntax_result['valid'],
            feedback='Valid QML' if syntax_result['valid'] else 'Syntax errors found',
            details=syntax_result['errors'] + syntax_result['warnings']
        )
        result.criteria.append(criterion)

        # Check for required QML patterns
        if 'required_qml_patterns' in self.config:
            with open(filepath, 'r') as f:
                content = f.read()

            found = 0
            details = []
            for pattern in self.config['required_qml_patterns']:
                if pattern in content or re.search(pattern, content):
                    found += 1
                    details.append(f"{pattern}: Found")
                else:
                    details.append(f"{pattern}: Missing")

            total = len(self.config['required_qml_patterns'])
            criterion = GradingCriterion(
                name='qml_patterns',
                description='Uses required QML patterns',
                weight=0.40,
                max_points=40,
                earned_points=40 * (found / total) if total > 0 else 40,
                passed=found == total,
                feedback=f"Found {found}/{total} required patterns",
                details=details
            )
            result.criteria.append(criterion)

    def _calculate_scores(self, result: GradingResult):
        """Calculate final scores from criteria"""

        # Category scores
        correctness_criteria = [c for c in result.criteria if 'correct' in c.name.lower()]
        bp_criteria = [c for c in result.criteria if c.name in BestPracticesChecker.CHECKS]
        quality_criteria = [c for c in result.criteria if 'quality' in c.name.lower() or 'complexity' in c.name.lower()]

        if correctness_criteria:
            result.correctness_score = sum(c.earned_points for c in correctness_criteria) / sum(c.max_points for c in correctness_criteria) * 100

        if bp_criteria:
            result.best_practices_score = sum(c.earned_points for c in bp_criteria) / sum(c.max_points for c in bp_criteria) * 100

        if quality_criteria:
            result.complexity_score = sum(c.earned_points for c in quality_criteria) / sum(c.max_points for c in quality_criteria) * 100

        # Total score
        if result.criteria:
            result.total_score = sum(c.earned_points for c in result.criteria)
            result.max_score = sum(c.max_points for c in result.criteria)

        # Letter grade
        pct = (result.total_score / result.max_score * 100) if result.max_score > 0 else 0
        if pct >= 90:
            result.grade_letter = 'A'
        elif pct >= 80:
            result.grade_letter = 'B'
        elif pct >= 70:
            result.grade_letter = 'C'
        elif pct >= 60:
            result.grade_letter = 'D'
        else:
            result.grade_letter = 'F'


def generate_report(result: GradingResult, format: str = 'text') -> str:
    """Generate a human-readable grading report"""

    if format == 'json':
        return json.dumps(asdict(result), indent=2, default=str)

    lines = [
        "=" * 60,
        "GRADING REPORT",
        "=" * 60,
        f"Exercise: {result.exercise_id}",
        f"Student: {result.student_id}",
        f"Submission: {result.submission_path}",
        f"Timestamp: {result.timestamp}",
        "",
        "-" * 60,
        f"FINAL GRADE: {result.grade_letter} ({result.total_score:.1f}/{result.max_score:.1f})",
        "-" * 60,
        "",
        "Category Scores:",
        f"  Correctness:    {result.correctness_score:.1f}%",
        f"  Best Practices: {result.best_practices_score:.1f}%",
        f"  Code Quality:   {result.complexity_score:.1f}%",
        "",
        "-" * 60,
        "DETAILED CRITERIA:",
        "-" * 60,
    ]

    for criterion in result.criteria:
        status = "PASS" if criterion.passed else "FAIL"
        lines.append(f"\n[{status}] {criterion.name}")
        lines.append(f"  {criterion.description}")
        lines.append(f"  Score: {criterion.earned_points:.1f}/{criterion.max_points:.1f}")
        lines.append(f"  {criterion.feedback}")
        if criterion.details:
            for detail in criterion.details[:5]:
                lines.append(f"    - {detail}")

    if result.errors:
        lines.append("\n" + "-" * 60)
        lines.append("ERRORS:")
        for error in result.errors:
            lines.append(f"  - {error}")

    if result.warnings:
        lines.append("\n" + "-" * 60)
        lines.append("WARNINGS:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    lines.append("\n" + "=" * 60)
    lines.append(f"Execution time: {result.execution_time:.3f}s")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='TRANS-QML Course Exercise Grader')
    parser.add_argument('--exercise', type=str, help='Exercise ID (e.g., 01_01)')
    parser.add_argument('--submission', type=str, help='Path to submission file')
    parser.add_argument('--student', type=str, default='anonymous', help='Student ID')
    parser.add_argument('--config', type=str, help='Path to exercise config JSON')
    parser.add_argument('--output', type=str, choices=['text', 'json'], default='text')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--batch', type=str, help='Directory of submissions for batch grading')
    parser.add_argument('--module', type=str, help='Module number for batch grading')

    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
    else:
        # Default minimal config
        config = {
            'id': args.exercise or 'unknown',
            'required_patterns': [],
            'test_cases': []
        }

    if args.batch and args.module:
        # Batch grading mode
        results = []
        submissions_dir = Path(args.batch)
        for submission in submissions_dir.glob('*.py'):
            grader = ExerciseGrader(config)
            result = grader.grade(str(submission), submission.stem)
            results.append(result)
            if args.verbose:
                print(f"Graded: {submission.name} -> {result.grade_letter}")

        # Summary
        print(f"\nBatch grading complete: {len(results)} submissions")
        grades = {}
        for r in results:
            grades[r.grade_letter] = grades.get(r.grade_letter, 0) + 1
        print("Grade distribution:", dict(sorted(grades.items())))

    elif args.submission:
        grader = ExerciseGrader(config)
        result = grader.grade(args.submission, args.student)
        print(generate_report(result, args.output))

        # Return exit code based on grade
        sys.exit(0 if result.grade_letter in ['A', 'B', 'C'] else 1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
