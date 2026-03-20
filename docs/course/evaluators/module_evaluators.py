#!/usr/bin/env python3
"""
Module-specific evaluators for TRANS-QML Course

Provides specialized evaluation for different exercise types:
- Python files (modules 1-8, 10)
- QML files (modules 1, 2, 5, 7)
- Makefiles (module 9)
- PyInstaller spec files (module 9)
"""

import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class EvalResult:
    """Result of evaluating a single pattern or test"""
    name: str
    passed: bool
    message: str
    score: float = 0.0
    max_score: float = 1.0


class MakefileEvaluator:
    """Evaluator for Makefile exercises"""

    REQUIRED_TARGETS = ['install', 'run', 'test', 'clean']
    BONUS_TARGETS = ['build', 'dist', 'lint', 'help']

    def evaluate(self, filepath: str, required_patterns: List[str] = None) -> List[EvalResult]:
        """Evaluate a Makefile submission"""
        results = []

        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except Exception as e:
            return [EvalResult(
                name='file_read',
                passed=False,
                message=f"Could not read file: {e}"
            )]

        # Check for .PHONY declaration
        has_phony = '.PHONY' in content
        results.append(EvalResult(
            name='.PHONY declaration',
            passed=has_phony,
            message='Found .PHONY declaration' if has_phony else 'Missing .PHONY declaration',
            score=1.0 if has_phony else 0.0
        ))

        # Check required targets
        for target in self.REQUIRED_TARGETS:
            pattern = rf'^{target}\s*:'
            found = bool(re.search(pattern, content, re.MULTILINE))
            results.append(EvalResult(
                name=f'target_{target}',
                passed=found,
                message=f"Target '{target}' found" if found else f"Missing target '{target}'",
                score=2.0 if found else 0.0,
                max_score=2.0
            ))

        # Check bonus targets
        for target in self.BONUS_TARGETS:
            pattern = rf'^{target}\s*:'
            found = bool(re.search(pattern, content, re.MULTILINE))
            if found:
                results.append(EvalResult(
                    name=f'bonus_target_{target}',
                    passed=True,
                    message=f"Bonus target '{target}' found",
                    score=0.5,
                    max_score=0.5
                ))

        # Check for variable definitions
        var_pattern = r'^[A-Z_]+\s*:?='
        variables = re.findall(var_pattern, content, re.MULTILINE)
        has_variables = len(variables) >= 2
        results.append(EvalResult(
            name='variables',
            passed=has_variables,
            message=f"Found {len(variables)} variable definitions",
            score=1.0 if has_variables else 0.5,
            max_score=1.0
        ))

        # Check for custom patterns from config
        if required_patterns:
            for pattern in required_patterns:
                found = bool(re.search(pattern, content, re.MULTILINE))
                results.append(EvalResult(
                    name=f'pattern_{pattern[:20]}',
                    passed=found,
                    message=f"Pattern '{pattern}' {'found' if found else 'not found'}",
                    score=1.0 if found else 0.0
                ))

        return results


class SpecFileEvaluator:
    """Evaluator for PyInstaller spec files"""

    REQUIRED_COMPONENTS = ['Analysis', 'PYZ', 'EXE', 'COLLECT']
    IMPORTANT_CONFIGS = ['hiddenimports', 'datas', 'name']

    def evaluate(self, filepath: str, required_patterns: List[str] = None) -> List[EvalResult]:
        """Evaluate a PyInstaller spec file"""
        results = []

        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except Exception as e:
            return [EvalResult(
                name='file_read',
                passed=False,
                message=f"Could not read file: {e}"
            )]

        # Check it's valid Python syntax (spec files are Python)
        try:
            compile(content, filepath, 'exec')
            results.append(EvalResult(
                name='syntax',
                passed=True,
                message='Valid Python syntax',
                score=2.0,
                max_score=2.0
            ))
        except SyntaxError as e:
            results.append(EvalResult(
                name='syntax',
                passed=False,
                message=f'Syntax error: {e}',
                score=0.0,
                max_score=2.0
            ))
            return results

        # Check required components
        for component in self.REQUIRED_COMPONENTS:
            pattern = rf'{component}\s*\('
            found = bool(re.search(pattern, content))
            results.append(EvalResult(
                name=f'component_{component}',
                passed=found,
                message=f"{component} {'found' if found else 'missing'}",
                score=2.0 if found else 0.0,
                max_score=2.0
            ))

        # Check important configurations
        for config in self.IMPORTANT_CONFIGS:
            found = config in content
            results.append(EvalResult(
                name=f'config_{config}',
                passed=found,
                message=f"Config '{config}' {'specified' if found else 'not specified'}",
                score=1.0 if found else 0.0,
                max_score=1.0
            ))

        # Check for custom patterns
        if required_patterns:
            for pattern in required_patterns:
                found = bool(re.search(pattern, content))
                results.append(EvalResult(
                    name=f'pattern_{pattern[:20]}',
                    passed=found,
                    message=f"Pattern '{pattern}' {'found' if found else 'not found'}",
                    score=1.0 if found else 0.0
                ))

        # Bonus: Check for macOS BUNDLE
        if 'BUNDLE' in content:
            results.append(EvalResult(
                name='bonus_macos_bundle',
                passed=True,
                message='macOS BUNDLE configuration found',
                score=1.0,
                max_score=1.0
            ))

        return results


class ComplexityEvaluator:
    """Evaluator for code complexity analysis exercises (Module 10)"""

    def evaluate(self, filepath: str, required_patterns: List[str] = None) -> List[EvalResult]:
        """Evaluate a complexity analyzer submission"""
        import ast

        results = []

        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except Exception as e:
            return [EvalResult(
                name='file_read',
                passed=False,
                message=f"Could not read file: {e}"
            )]

        # Parse to check syntax
        try:
            tree = ast.parse(content)
            results.append(EvalResult(
                name='syntax',
                passed=True,
                message='Valid Python syntax',
                score=2.0,
                max_score=2.0
            ))
        except SyntaxError as e:
            return [EvalResult(
                name='syntax',
                passed=False,
                message=f'Syntax error: {e}',
                score=0.0
            )]

        # Check for AST usage
        uses_ast = 'import ast' in content or 'from ast import' in content
        results.append(EvalResult(
            name='uses_ast',
            passed=uses_ast,
            message='Uses ast module' if uses_ast else 'Missing ast module import',
            score=2.0 if uses_ast else 0.0,
            max_score=2.0
        ))

        # Check for NodeVisitor
        uses_visitor = 'NodeVisitor' in content
        results.append(EvalResult(
            name='uses_visitor',
            passed=uses_visitor,
            message='Uses NodeVisitor pattern' if uses_visitor else 'Missing NodeVisitor',
            score=2.0 if uses_visitor else 0.0,
            max_score=2.0
        ))

        # Check for complexity calculation
        calc_complexity = any(p in content.lower() for p in ['complexity', 'cyclomatic'])
        results.append(EvalResult(
            name='calculates_complexity',
            passed=calc_complexity,
            message='Calculates complexity' if calc_complexity else 'Missing complexity calculation',
            score=3.0 if calc_complexity else 0.0,
            max_score=3.0
        ))

        # Check for nesting depth
        calc_nesting = any(p in content.lower() for p in ['nesting', 'depth'])
        results.append(EvalResult(
            name='calculates_nesting',
            passed=calc_nesting,
            message='Tracks nesting depth' if calc_nesting else 'Missing nesting depth tracking',
            score=2.0 if calc_nesting else 0.0,
            max_score=2.0
        ))

        # Check for dataclass usage
        uses_dataclass = '@dataclass' in content
        results.append(EvalResult(
            name='uses_dataclass',
            passed=uses_dataclass,
            message='Uses dataclass for metrics' if uses_dataclass else 'Consider using dataclass',
            score=1.0 if uses_dataclass else 0.0,
            max_score=1.0
        ))

        # Custom patterns
        if required_patterns:
            for pattern in required_patterns:
                found = bool(re.search(pattern, content, re.IGNORECASE))
                results.append(EvalResult(
                    name=f'pattern_{pattern[:20]}',
                    passed=found,
                    message=f"Pattern '{pattern}' {'found' if found else 'not found'}",
                    score=1.0 if found else 0.0
                ))

        return results


class JSONLoggerEvaluator:
    """Evaluator for JSON logging exercises (Module 9)"""

    def evaluate(self, filepath: str, required_patterns: List[str] = None) -> List[EvalResult]:
        """Evaluate a JSON logger submission"""
        import ast

        results = []

        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except Exception as e:
            return [EvalResult(
                name='file_read',
                passed=False,
                message=f"Could not read file: {e}"
            )]

        # Parse to check syntax
        try:
            tree = ast.parse(content)
            results.append(EvalResult(
                name='syntax',
                passed=True,
                message='Valid Python syntax',
                score=2.0,
                max_score=2.0
            ))
        except SyntaxError:
            return [EvalResult(
                name='syntax',
                passed=False,
                message='Syntax error',
                score=0.0
            )]

        # Check for logging import
        uses_logging = 'import logging' in content or 'from logging' in content
        results.append(EvalResult(
            name='imports_logging',
            passed=uses_logging,
            message='Imports logging module' if uses_logging else 'Missing logging import',
            score=1.0 if uses_logging else 0.0
        ))

        # Check for json import
        uses_json = 'import json' in content or 'from json' in content
        results.append(EvalResult(
            name='imports_json',
            passed=uses_json,
            message='Imports json module' if uses_json else 'Missing json import',
            score=1.0 if uses_json else 0.0
        ))

        # Check for Formatter subclass
        has_formatter = 'Formatter' in content and 'class' in content
        results.append(EvalResult(
            name='has_formatter_class',
            passed=has_formatter,
            message='Has Formatter class' if has_formatter else 'Missing Formatter subclass',
            score=2.0 if has_formatter else 0.0,
            max_score=2.0
        ))

        # Check for format method
        has_format = 'def format' in content
        results.append(EvalResult(
            name='has_format_method',
            passed=has_format,
            message='Has format method' if has_format else 'Missing format method',
            score=2.0 if has_format else 0.0,
            max_score=2.0
        ))

        # Check for json.dumps
        uses_dumps = 'json.dumps' in content
        results.append(EvalResult(
            name='uses_json_dumps',
            passed=uses_dumps,
            message='Uses json.dumps' if uses_dumps else 'Missing json.dumps call',
            score=2.0 if uses_dumps else 0.0,
            max_score=2.0
        ))

        # Check for timestamp
        has_timestamp = any(p in content for p in ['timestamp', 'datetime', 'time.time'])
        results.append(EvalResult(
            name='has_timestamp',
            passed=has_timestamp,
            message='Includes timestamp' if has_timestamp else 'Missing timestamp in output',
            score=1.0 if has_timestamp else 0.0
        ))

        # Custom patterns
        if required_patterns:
            for pattern in required_patterns:
                found = bool(re.search(pattern, content, re.IGNORECASE))
                results.append(EvalResult(
                    name=f'pattern_{pattern[:20]}',
                    passed=found,
                    message=f"Pattern '{pattern}' {'found' if found else 'not found'}",
                    score=1.0 if found else 0.0
                ))

        return results


def get_evaluator_for_exercise(exercise_id: str, file_type: str = None):
    """Get appropriate evaluator based on exercise ID and file type"""

    module = exercise_id.split('_')[0] if '_' in exercise_id else exercise_id[:2]

    if file_type == 'makefile' or (module == '09' and '01' in exercise_id):
        return MakefileEvaluator()
    elif file_type == 'spec' or (module == '09' and '02' in exercise_id):
        return SpecFileEvaluator()
    elif module == '10':
        return ComplexityEvaluator()
    elif module == '09' and '03' in exercise_id:
        return JSONLoggerEvaluator()

    return None  # Use default Python/QML evaluator


def load_all_exercises() -> Dict[str, Any]:
    """Load all exercise configurations from all modules"""
    exercises_dir = Path(__file__).parent.parent / 'exercises'
    all_exercises = {}

    for module_dir in exercises_dir.iterdir():
        if module_dir.is_dir() and module_dir.name.startswith('module'):
            config_file = module_dir / 'exercises.json'
            if config_file.exists():
                with open(config_file) as f:
                    module_config = json.load(f)
                    for ex in module_config.get('exercises', []):
                        all_exercises[ex['id']] = ex
                    for ex in module_config.get('extra_exercises', []):
                        all_exercises[ex['id']] = ex

    # Load extra pack
    extra_file = exercises_dir / 'extra' / 'exercises.json'
    if extra_file.exists():
        with open(extra_file) as f:
            extra_config = json.load(f)
            for ex in extra_config.get('exercises', []):
                all_exercises[ex['id']] = ex
            for ex in extra_config.get('mini_challenges', []):
                all_exercises[ex['id']] = ex

    return all_exercises


if __name__ == '__main__':
    # Test loading exercises
    exercises = load_all_exercises()
    print(f"Loaded {len(exercises)} exercises")

    for ex_id, ex in list(exercises.items())[:5]:
        print(f"  {ex_id}: {ex.get('title', 'Untitled')}")
