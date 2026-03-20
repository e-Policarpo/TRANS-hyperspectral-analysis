# Module 10: Code Complexity Analysis

## Understanding and Measuring Code Quality

This module teaches you to analyze and measure code complexity, identify maintainability issues, and build automated quality assessment tools. These skills are essential for writing maintainable scientific software.

---

## Learning Objectives

By the end of this module, you will be able to:
- Calculate cyclomatic complexity for Python functions
- Measure nesting depth and cognitive complexity
- Build AST-based code analyzers
- Create automated quality reports
- Apply complexity analysis to real TRANS-QML code

---

## 10.1 Why Code Complexity Matters

### The Cost of Complexity

Complex code leads to:
- **More bugs** - Complex code has more paths to fail
- **Harder maintenance** - Understanding takes longer
- **Testing difficulty** - More paths = more test cases needed
- **Slower onboarding** - New developers struggle

### Complexity Metrics

| Metric | What It Measures | Good Values |
|--------|------------------|-------------|
| Cyclomatic Complexity | Number of decision paths | < 10 |
| Nesting Depth | Maximum indentation level | < 4 |
| Cognitive Complexity | Mental effort to understand | < 15 |
| Lines of Code (LOC) | Function/class size | < 50 per function |
| Halstead Metrics | Computational complexity | Varies |

---

## 10.2 Cyclomatic Complexity

### Definition

Cyclomatic complexity (CC) counts the number of linearly independent paths through code:

```
CC = E - N + 2P

Where:
E = number of edges (control flow transitions)
N = number of nodes (statements)
P = number of connected components (usually 1)
```

### Simpler Calculation

For practical purposes:

```
CC = 1 + number of decision points

Decision points:
- if/elif
- for
- while
- except
- and/or in conditions
- ternary expressions
```

### Example

```python
def calculate_grade(score, curve=0):
    """
    Cyclomatic Complexity = 6

    Decision points:
    1. if score < 0
    2. if score > 100
    3. if score >= 90
    4. elif score >= 80
    5. elif score >= 70
    """
    score = score + curve

    if score < 0:           # +1
        return "Invalid"
    if score > 100:         # +1
        score = 100

    if score >= 90:         # +1
        return "A"
    elif score >= 80:       # +1
        return "B"
    elif score >= 70:       # +1
        return "C"
    else:
        return "F"
```

### Python Implementation

```python
import ast
from typing import Set


class CyclomaticComplexityVisitor(ast.NodeVisitor):
    """
    Calculate cyclomatic complexity of Python code.

    Counts:
    - if/elif statements
    - for/while loops
    - except handlers
    - boolean operators (and/or)
    - conditional expressions (ternary)
    - comprehensions with conditions
    """

    def __init__(self):
        self.complexity = 1  # Base complexity

    def visit_If(self, node: ast.If):
        """Count if statements"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        """Count for loops"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        """Count while loops"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Count except handlers"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        """Count boolean operators (and/or add paths)"""
        # Each 'and'/'or' adds a decision point
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp):
        """Count ternary expressions"""
        self.complexity += 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension):
        """Count comprehension conditions"""
        self.complexity += len(node.ifs)
        self.generic_visit(node)


def calculate_cyclomatic_complexity(source_code: str) -> int:
    """
    Calculate cyclomatic complexity of Python source code.

    Parameters:
        source_code: Python source code string

    Returns:
        Cyclomatic complexity value
    """
    tree = ast.parse(source_code)
    visitor = CyclomaticComplexityVisitor()
    visitor.visit(tree)
    return visitor.complexity


def get_function_complexities(source_code: str) -> dict:
    """
    Get complexity for each function in source code.

    Returns:
        Dict mapping function names to complexity values
    """
    tree = ast.parse(source_code)
    results = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Get just this function's source
            func_source = ast.unparse(node)
            complexity = calculate_cyclomatic_complexity(func_source)
            results[node.name] = complexity

    return results
```

---

## 10.3 Nesting Depth

### Why Nesting Matters

Deeply nested code is hard to follow:

```python
# Bad: Deep nesting (depth = 5)
def process_data(data):
    if data:
        for item in data:
            if item.valid:
                for field in item.fields:
                    if field.type == "numeric":
                        # Hard to understand context
                        process_numeric(field)

# Good: Early returns (depth = 2)
def process_data(data):
    if not data:
        return

    for item in data:
        if not item.valid:
            continue

        process_valid_item(item)
```

### Measuring Nesting Depth

```python
class NestingDepthVisitor(ast.NodeVisitor):
    """
    Calculate maximum nesting depth of Python code.

    Tracks depth through:
    - if/elif/else
    - for/while
    - with statements
    - try/except/finally
    - function/class definitions
    """

    def __init__(self):
        self.max_depth = 0
        self.current_depth = 0

    def _visit_block(self, node):
        """Visit a node that increases nesting"""
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_If(self, node):
        self._visit_block(node)

    def visit_For(self, node):
        self._visit_block(node)

    def visit_While(self, node):
        self._visit_block(node)

    def visit_With(self, node):
        self._visit_block(node)

    def visit_Try(self, node):
        self._visit_block(node)

    def visit_FunctionDef(self, node):
        self._visit_block(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_block(node)

    def visit_ClassDef(self, node):
        self._visit_block(node)


def calculate_nesting_depth(source_code: str) -> int:
    """
    Calculate maximum nesting depth of Python source code.

    Parameters:
        source_code: Python source code string

    Returns:
        Maximum nesting depth
    """
    tree = ast.parse(source_code)
    visitor = NestingDepthVisitor()
    visitor.visit(tree)
    return visitor.max_depth
```

---

## 10.4 Cognitive Complexity

### Beyond Cyclomatic Complexity

Cognitive complexity measures how hard code is to *understand*, not just how many paths exist:

```python
# Same cyclomatic complexity (2), different cognitive complexity

# Lower cognitive complexity - flat structure
def is_adult(age):
    if age >= 18:
        return True
    return False

# Higher cognitive complexity - nested
def is_adult_complex(person):
    if person:
        if person.age:
            if person.age >= 18:
                return True
    return False
```

### Cognitive Complexity Rules

1. **Increment for nesting**: Each level of nesting adds penalty
2. **Increment for breaks in flow**: `else`, `elif`, `except`
3. **Don't count all branches equally**: `else if` chains penalized less

```python
class CognitiveComplexityVisitor(ast.NodeVisitor):
    """
    Calculate cognitive complexity.

    Rules:
    - +1 for each control structure (if, for, while, etc.)
    - +1 for nesting (multiplied by depth)
    - +1 for breaks in flow (else, elif)
    """

    def __init__(self):
        self.complexity = 0
        self.nesting_level = 0

    def _increment(self, node, base=1):
        """Add complexity with nesting penalty"""
        self.complexity += base + self.nesting_level

    def visit_If(self, node):
        self._increment(node)

        # Visit condition and body
        self.nesting_level += 1
        for child in node.body:
            self.visit(child)
        self.nesting_level -= 1

        # Handle else/elif
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

    def visit_For(self, node):
        self._increment(node)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_While(self, node):
        self._increment(node)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_BoolOp(self, node):
        # Binary sequences add to complexity
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Break(self, node):
        self.complexity += 1

    def visit_Continue(self, node):
        self.complexity += 1

    def visit_Try(self, node):
        self.nesting_level += 1
        for child in node.body:
            self.visit(child)
        self.nesting_level -= 1

        for handler in node.handlers:
            self._increment(handler)
            self.nesting_level += 1
            for child in handler.body:
                self.visit(child)
            self.nesting_level -= 1


def calculate_cognitive_complexity(source_code: str) -> int:
    """Calculate cognitive complexity of Python source"""
    tree = ast.parse(source_code)
    visitor = CognitiveComplexityVisitor()
    visitor.visit(tree)
    return visitor.complexity
```

---

## 10.5 Building a Code Analyzer

### Complete Analyzer Class

```python
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


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
    functions: List[FunctionMetrics]
    classes: List[ClassMetrics]
    imports: int

    @property
    def average_complexity(self) -> float:
        if not self.functions:
            return 0.0
        total = sum(f.cyclomatic_complexity for f in self.functions)
        return total / len(self.functions)


class CodeAnalyzer:
    """
    Comprehensive code quality analyzer.

    Analyzes Python source files for:
    - Cyclomatic complexity
    - Nesting depth
    - Cognitive complexity
    - Lines of code
    - Function/class metrics
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
        source = filepath.read_text()
        tree = ast.parse(source)

        # Count lines
        lines = source.split('\n')
        total_lines = len(lines)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('#'))
        comment_lines = sum(1 for line in lines if line.strip().startswith('#'))

        # Analyze functions
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_metrics = self._analyze_function(node, source)
                functions.append(func_metrics)

        # Analyze classes
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_metrics = self._analyze_class(node)
                classes.append(class_metrics)

        # Count imports
        imports = sum(1 for node in ast.walk(tree)
                     if isinstance(node, (ast.Import, ast.ImportFrom)))

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

    def _analyze_function(self, node: ast.FunctionDef, source: str) -> FunctionMetrics:
        """Analyze a function definition"""
        # Get function source
        func_source = ast.unparse(node)

        # Calculate metrics
        cc = calculate_cyclomatic_complexity(func_source)
        nesting = calculate_nesting_depth(func_source)
        cognitive = calculate_cognitive_complexity(func_source)

        # Count lines
        if hasattr(node, 'end_lineno'):
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
        methods = sum(1 for n in node.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))

        # Count class-level assignments as attributes
        attributes = sum(1 for n in node.body if isinstance(n, ast.Assign))

        # Calculate inheritance depth (simplified)
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
                except SyntaxError as e:
                    print(f"Syntax error in {py_file}: {e}")

        return self.metrics

    def generate_report(self) -> str:
        """Generate a text report of all analyzed files"""
        lines = ["Code Complexity Report", "=" * 60, ""]

        for filepath, metrics in self.metrics.items():
            lines.append(f"File: {filepath}")
            lines.append(f"  Lines: {metrics.total_lines} total, {metrics.code_lines} code")
            lines.append(f"  Average Complexity: {metrics.average_complexity:.2f}")
            lines.append("")

            # Functions with high complexity
            high_complexity = [f for f in metrics.functions if f.cyclomatic_complexity > 10]
            if high_complexity:
                lines.append("  High Complexity Functions:")
                for func in high_complexity:
                    lines.append(f"    - {func.name}: CC={func.cyclomatic_complexity}, "
                               f"Nesting={func.nesting_depth}")
            lines.append("")

        return "\n".join(lines)

    def get_issues(self) -> List[dict]:
        """
        Get list of quality issues.

        Returns:
            List of issue dicts with severity, location, message
        """
        issues = []

        for filepath, metrics in self.metrics.items():
            for func in metrics.functions:
                # High cyclomatic complexity
                if func.cyclomatic_complexity > 10:
                    issues.append({
                        'severity': 'warning' if func.cyclomatic_complexity <= 15 else 'error',
                        'file': filepath,
                        'line': func.lineno,
                        'function': func.name,
                        'type': 'cyclomatic_complexity',
                        'value': func.cyclomatic_complexity,
                        'message': f"Function '{func.name}' has high cyclomatic complexity "
                                  f"({func.cyclomatic_complexity}). Consider refactoring."
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
                        'message': f"Function '{func.name}' has deep nesting "
                                  f"(depth={func.nesting_depth}). Consider flattening."
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
                        'message': f"Function '{func.name}' has many parameters "
                                  f"({func.parameters}). Consider using a data class."
                    })

        return issues
```

---

## 10.6 Applying to TRANS-QML

### Analyzing TRANS Backend

```python
from pathlib import Path


def analyze_trans_codebase():
    """Analyze the TRANS-QML codebase"""
    analyzer = CodeAnalyzer()

    # Analyze backend
    backend_path = Path("src/backend")
    analyzer.analyze_directory(backend_path)

    # Analyze widgets
    widgets_path = Path("src/widgets")
    analyzer.analyze_directory(widgets_path)

    # Analyze models
    models_path = Path("src/models")
    analyzer.analyze_directory(models_path)

    # Generate report
    print(analyzer.generate_report())

    # Get issues
    issues = analyzer.get_issues()
    print(f"\nFound {len(issues)} quality issues:\n")

    for issue in sorted(issues, key=lambda x: x['severity']):
        print(f"[{issue['severity'].upper()}] {issue['file']}:{issue['line']}")
        print(f"  {issue['message']}\n")

    return analyzer


if __name__ == "__main__":
    analyze_trans_codebase()
```

### Example Output

```
Code Complexity Report
============================================================

File: src/backend/app_backend.py
  Lines: 850 total, 720 code
  Average Complexity: 4.2

  High Complexity Functions:
    - runTool: CC=12, Nesting=3
    - _process_workflow: CC=15, Nesting=5

File: src/widgets/qml_profile_canvas.py
  Lines: 450 total, 380 code
  Average Complexity: 3.8

Found 3 quality issues:

[WARNING] src/backend/app_backend.py:245
  Function 'runTool' has high cyclomatic complexity (12). Consider refactoring.

[ERROR] src/backend/app_backend.py:512
  Function '_process_workflow' has high cyclomatic complexity (15). Consider refactoring.

[WARNING] src/backend/app_backend.py:512
  Function '_process_workflow' has deep nesting (depth=5). Consider flattening.
```

---

## 10.7 Integration with CI/CD

### Pre-commit Hook

```python
#!/usr/bin/env python3
# .git/hooks/pre-commit (make executable)
"""
Pre-commit hook that checks code complexity.
"""

import subprocess
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from complexity_analyzer import CodeAnalyzer


def get_staged_python_files():
    """Get list of staged Python files"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True
    )
    return [f for f in result.stdout.split('\n') if f.endswith('.py')]


def main():
    files = get_staged_python_files()
    if not files:
        return 0

    analyzer = CodeAnalyzer()
    for filepath in files:
        try:
            analyzer.analyze_file(Path(filepath))
        except Exception as e:
            print(f"Error analyzing {filepath}: {e}")
            continue

    issues = analyzer.get_issues()
    errors = [i for i in issues if i['severity'] == 'error']

    if errors:
        print("Commit blocked due to code complexity issues:\n")
        for issue in errors:
            print(f"  {issue['file']}:{issue['line']}")
            print(f"    {issue['message']}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### GitHub Actions Workflow

```yaml
# .github/workflows/complexity.yml
name: Code Complexity Check

on: [push, pull_request]

jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Run complexity analysis
        run: |
          python scripts/complexity_analyzer.py src/ > complexity_report.txt

      - name: Check for issues
        run: |
          if grep -q "ERROR" complexity_report.txt; then
            cat complexity_report.txt
            exit 1
          fi

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: complexity-report
          path: complexity_report.txt
```

---

## 10.8 Summary

### Key Metrics

| Metric | Formula | Threshold |
|--------|---------|-----------|
| Cyclomatic Complexity | 1 + decision points | < 10 |
| Nesting Depth | Max indentation levels | < 4 |
| Cognitive Complexity | Weighted nesting + flow breaks | < 15 |
| Lines per Function | Count | < 50 |
| Parameters | Function args | < 5 |

### Refactoring Strategies

When complexity is high:
1. **Extract functions** - Break into smaller pieces
2. **Early returns** - Reduce nesting with guard clauses
3. **Simplify conditions** - Use helper functions for complex logic
4. **Strategy pattern** - Replace conditional with polymorphism

---

## Exercises

### Exercise 10.1: Cyclomatic Complexity Calculator
Implement a function that calculates cyclomatic complexity using AST.

### Exercise 10.2: Nesting Depth Analyzer
Build a visitor that tracks maximum nesting depth.

### Exercise 10.3: Complete Code Analyzer
Create a CodeAnalyzer class that reports all metrics.

### Exercise 10.4: JSON Report Generator
Add a method that outputs analysis as JSON.

### Exercise 10.5: Analyze TRANS-QML
Run your analyzer on the TRANS backend and identify refactoring targets.

---

*Module 10 of 10 | TRANS-QML Course*
