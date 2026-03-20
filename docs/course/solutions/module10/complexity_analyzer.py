"""
Solution for Module 10 Exercises: Code Complexity Analyzer

A comprehensive code analyzer that calculates:
- Cyclomatic complexity
- Nesting depth
- Cognitive complexity
- Function and class metrics
"""

import ast
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class FunctionMetrics:
    """Metrics for a single function"""
    name: str
    lineno: int
    cyclomatic_complexity: int
    nesting_depth: int
    cognitive_complexity: int
    lines_of_code: int
    parameters: int
    returns: int


@dataclass
class ClassMetrics:
    """Metrics for a class"""
    name: str
    lineno: int
    methods: int
    attributes: int
    inheritance_depth: int


@dataclass
class FileMetrics:
    """Metrics for an entire file"""
    path: str
    total_lines: int
    code_lines: int
    comment_lines: int
    functions: List[FunctionMetrics] = field(default_factory=list)
    classes: List[ClassMetrics] = field(default_factory=list)
    imports: int = 0

    @property
    def average_complexity(self) -> float:
        """Calculate average cyclomatic complexity of all functions"""
        if not self.functions:
            return 0.0
        total = sum(f.cyclomatic_complexity for f in self.functions)
        return total / len(self.functions)


class CyclomaticComplexityVisitor(ast.NodeVisitor):
    """
    Calculate cyclomatic complexity of Python code.

    Cyclomatic complexity = 1 + number of decision points

    Decision points counted:
    - if/elif statements
    - for/while loops
    - except handlers
    - boolean operators (and/or)
    - conditional expressions (ternary)
    - comprehensions with conditions
    """

    def __init__(self):
        self.complexity = 1  # Base complexity

    def visit_If(self, node: ast.If) -> None:
        """Count if statements"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Count for loops"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        """Count while loops"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Count except handlers"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Count boolean operators (and/or add paths)"""
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        """Count ternary expressions"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        """Count comprehension conditions"""
        self.complexity += len(node.ifs)
        self.generic_visit(node)


class NestingDepthVisitor(ast.NodeVisitor):
    """
    Calculate maximum nesting depth of Python code.

    Tracks depth through:
    - if/elif/else blocks
    - for/while loops
    - with statements
    - try/except/finally blocks
    - function/class definitions
    """

    def __init__(self):
        self.max_depth = 0
        self.current_depth = 0

    def _visit_block(self, node: ast.AST) -> None:
        """Visit a node that increases nesting"""
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self._visit_block(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_block(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_block(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_block(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_block(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_block(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_block(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_block(node)


class CognitiveComplexityVisitor(ast.NodeVisitor):
    """
    Calculate cognitive complexity (SonarSource method).

    Cognitive complexity measures how hard code is to understand.
    It penalizes nesting and breaks in linear flow more heavily
    than cyclomatic complexity.
    """

    def __init__(self):
        self.complexity = 0
        self.nesting_level = 0

    def _increment(self, base: int = 1) -> None:
        """Add complexity with nesting penalty"""
        self.complexity += base + self.nesting_level

    def visit_If(self, node: ast.If) -> None:
        self._increment()
        self.nesting_level += 1
        for child in node.body:
            self.visit(child)
        self.nesting_level -= 1

        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                # elif - lower penalty
                self.complexity += 1
                self.visit(node.orelse[0])
            else:
                # else block
                self.complexity += 1
                self.nesting_level += 1
                for child in node.orelse:
                    self.visit(child)
                self.nesting_level -= 1

    def visit_For(self, node: ast.For) -> None:
        self._increment()
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_While(self, node: ast.While) -> None:
        self._increment()
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        self.complexity += 1

    def visit_Continue(self, node: ast.Continue) -> None:
        self.complexity += 1

    def visit_Try(self, node: ast.Try) -> None:
        self.nesting_level += 1
        for child in node.body:
            self.visit(child)
        self.nesting_level -= 1

        for handler in node.handlers:
            self._increment()
            self.nesting_level += 1
            for child in handler.body:
                self.visit(child)
            self.nesting_level -= 1


def calculate_cyclomatic_complexity(source_code: str) -> int:
    """
    Calculate cyclomatic complexity of Python source code.

    Parameters:
        source_code: Python source code string

    Returns:
        Cyclomatic complexity value (minimum 1)
    """
    try:
        tree = ast.parse(source_code)
        visitor = CyclomaticComplexityVisitor()
        visitor.visit(tree)
        return visitor.complexity
    except SyntaxError:
        return 0


def calculate_nesting_depth(source_code: str) -> int:
    """
    Calculate maximum nesting depth of Python source code.

    Parameters:
        source_code: Python source code string

    Returns:
        Maximum nesting depth
    """
    try:
        tree = ast.parse(source_code)
        visitor = NestingDepthVisitor()
        visitor.visit(tree)
        return visitor.max_depth
    except SyntaxError:
        return 0


def calculate_cognitive_complexity(source_code: str) -> int:
    """
    Calculate cognitive complexity of Python source code.

    Parameters:
        source_code: Python source code string

    Returns:
        Cognitive complexity value
    """
    try:
        tree = ast.parse(source_code)
        visitor = CognitiveComplexityVisitor()
        visitor.visit(tree)
        return visitor.complexity
    except SyntaxError:
        return 0


class CodeAnalyzer:
    """
    Comprehensive code quality analyzer for Python files.

    Analyzes Python source files for:
    - Cyclomatic complexity
    - Nesting depth
    - Cognitive complexity
    - Lines of code
    - Function/class metrics
    - Quality issues

    Example:
        analyzer = CodeAnalyzer()
        metrics = analyzer.analyze_file(Path("src/backend.py"))
        print(analyzer.generate_report())
    """

    def __init__(self):
        self.metrics: Dict[str, FileMetrics] = {}

    def analyze_file(self, filepath: Path) -> FileMetrics:
        """
        Analyze a single Python file.

        Parameters:
            filepath: Path to Python file

        Returns:
            FileMetrics for the file
        """
        source = filepath.read_text(encoding='utf-8')
        tree = ast.parse(source)

        # Count lines
        lines = source.split('\n')
        total_lines = len(lines)
        code_lines = sum(
            1 for line in lines
            if line.strip() and not line.strip().startswith('#')
        )
        comment_lines = sum(
            1 for line in lines
            if line.strip().startswith('#')
        )

        # Analyze functions
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_metrics = self._analyze_function(node)
                functions.append(func_metrics)

        # Analyze classes
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_metrics = self._analyze_class(node)
                classes.append(class_metrics)

        # Count imports
        imports = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        )

        metrics = FileMetrics(
            path=str(filepath),
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            functions=functions,
            classes=classes,
            imports=imports
        )

        self.metrics[str(filepath)] = metrics
        return metrics

    def _analyze_function(self, node: ast.FunctionDef) -> FunctionMetrics:
        """Analyze a function definition"""
        func_source = ast.unparse(node)

        cc = calculate_cyclomatic_complexity(func_source)
        nesting = calculate_nesting_depth(func_source)
        cognitive = calculate_cognitive_complexity(func_source)

        # Count lines
        if hasattr(node, 'end_lineno') and node.end_lineno:
            loc = node.end_lineno - node.lineno + 1
        else:
            loc = func_source.count('\n') + 1

        # Count parameters
        params = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            params += 1
        if node.args.kwarg:
            params += 1

        # Count returns
        returns = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))

        return FunctionMetrics(
            name=node.name,
            lineno=node.lineno,
            cyclomatic_complexity=cc,
            nesting_depth=nesting,
            cognitive_complexity=cognitive,
            lines_of_code=loc,
            parameters=params,
            returns=returns
        )

    def _analyze_class(self, node: ast.ClassDef) -> ClassMetrics:
        """Analyze a class definition"""
        methods = sum(
            1 for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

        attributes = sum(1 for n in node.body if isinstance(n, ast.Assign))
        inheritance_depth = len(node.bases)

        return ClassMetrics(
            name=node.name,
            lineno=node.lineno,
            methods=methods,
            attributes=attributes,
            inheritance_depth=inheritance_depth
        )

    def analyze_directory(self, directory: Path) -> Dict[str, FileMetrics]:
        """
        Analyze all Python files in a directory.

        Parameters:
            directory: Path to directory

        Returns:
            Dict mapping file paths to FileMetrics
        """
        for py_file in directory.rglob("*.py"):
            if "__pycache__" not in str(py_file):
                try:
                    self.analyze_file(py_file)
                except (SyntaxError, UnicodeDecodeError) as e:
                    print(f"Error in {py_file}: {e}")

        return self.metrics

    def generate_report(self) -> str:
        """Generate a text report of all analyzed files"""
        lines = [
            "Code Complexity Report",
            "=" * 60,
            ""
        ]

        for filepath, metrics in self.metrics.items():
            lines.append(f"File: {filepath}")
            lines.append(f"  Lines: {metrics.total_lines} total, "
                        f"{metrics.code_lines} code, "
                        f"{metrics.comment_lines} comments")
            lines.append(f"  Average Complexity: {metrics.average_complexity:.2f}")
            lines.append(f"  Functions: {len(metrics.functions)}, "
                        f"Classes: {len(metrics.classes)}")
            lines.append("")

            # High complexity functions
            high_cc = [f for f in metrics.functions if f.cyclomatic_complexity > 10]
            if high_cc:
                lines.append("  High Complexity Functions:")
                for func in high_cc:
                    lines.append(
                        f"    - {func.name} (line {func.lineno}): "
                        f"CC={func.cyclomatic_complexity}, "
                        f"Nesting={func.nesting_depth}"
                    )
                lines.append("")

        return "\n".join(lines)

    def generate_json_report(self) -> str:
        """Generate a JSON report of all analyzed files"""
        report: Dict[str, Any] = {
            "summary": {
                "total_files": len(self.metrics),
                "total_functions": sum(
                    len(m.functions) for m in self.metrics.values()
                ),
                "total_classes": sum(
                    len(m.classes) for m in self.metrics.values()
                )
            },
            "files": {}
        }

        for filepath, metrics in self.metrics.items():
            report["files"][filepath] = {
                "total_lines": metrics.total_lines,
                "code_lines": metrics.code_lines,
                "average_complexity": round(metrics.average_complexity, 2),
                "functions": [asdict(f) for f in metrics.functions],
                "classes": [asdict(c) for c in metrics.classes]
            }

        return json.dumps(report, indent=2)

    def get_issues(self) -> List[Dict[str, Any]]:
        """
        Get list of quality issues found during analysis.

        Returns:
            List of issue dicts with severity, location, message
        """
        issues = []

        for filepath, metrics in self.metrics.items():
            for func in metrics.functions:
                # High cyclomatic complexity
                if func.cyclomatic_complexity > 10:
                    severity = 'warning' if func.cyclomatic_complexity <= 15 else 'error'
                    issues.append({
                        'severity': severity,
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'cyclomatic_complexity',
                        'value': func.cyclomatic_complexity,
                        'threshold': 10,
                        'message': f"Function '{func.name}' has high cyclomatic "
                                  f"complexity ({func.cyclomatic_complexity}). "
                                  f"Consider refactoring into smaller functions."
                    })

                # Deep nesting
                if func.nesting_depth > 4:
                    issues.append({
                        'severity': 'warning',
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'nesting_depth',
                        'value': func.nesting_depth,
                        'threshold': 4,
                        'message': f"Function '{func.name}' has deep nesting "
                                  f"(depth={func.nesting_depth}). Consider using "
                                  f"early returns or extracting helper functions."
                    })

                # High cognitive complexity
                if func.cognitive_complexity > 15:
                    issues.append({
                        'severity': 'warning',
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'cognitive_complexity',
                        'value': func.cognitive_complexity,
                        'threshold': 15,
                        'message': f"Function '{func.name}' has high cognitive "
                                  f"complexity ({func.cognitive_complexity}). "
                                  f"This code may be difficult to understand."
                    })

                # Too many parameters
                if func.parameters > 5:
                    issues.append({
                        'severity': 'info',
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'too_many_parameters',
                        'value': func.parameters,
                        'threshold': 5,
                        'message': f"Function '{func.name}' has many parameters "
                                  f"({func.parameters}). Consider using a data "
                                  f"class or configuration object."
                    })

                # Long function
                if func.lines_of_code > 50:
                    issues.append({
                        'severity': 'info',
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'long_function',
                        'value': func.lines_of_code,
                        'threshold': 50,
                        'message': f"Function '{func.name}' is quite long "
                                  f"({func.lines_of_code} lines). Consider "
                                  f"breaking it into smaller functions."
                    })

        return issues


# Example usage and test
if __name__ == "__main__":
    # Test code with known complexity
    test_code = '''
def complex_function(data, options=None):
    """A function with moderate complexity for testing"""
    if not data:
        return None

    result = []
    for item in data:
        if item.valid:
            if item.type == "A":
                result.append(process_a(item))
            elif item.type == "B":
                result.append(process_b(item))
            else:
                result.append(item)
        else:
            if options and options.get("include_invalid"):
                result.append(None)

    return result


def simple_function(x):
    """A simple function"""
    return x * 2
'''

    # Test individual metrics
    print("Cyclomatic Complexity:", calculate_cyclomatic_complexity(test_code))
    print("Nesting Depth:", calculate_nesting_depth(test_code))
    print("Cognitive Complexity:", calculate_cognitive_complexity(test_code))
    print()

    # Test full analyzer
    analyzer = CodeAnalyzer()

    # Save test code to temp file for analysis
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_code)
        temp_path = Path(f.name)

    metrics = analyzer.analyze_file(temp_path)
    print(analyzer.generate_report())
    print("\nJSON Report:")
    print(analyzer.generate_json_report())
    print("\nIssues Found:")
    for issue in analyzer.get_issues():
        print(f"  [{issue['severity'].upper()}] {issue['message']}")

    # Cleanup
    temp_path.unlink()
