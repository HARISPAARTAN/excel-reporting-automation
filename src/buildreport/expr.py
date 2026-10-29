"""Metric expressions from report.yaml: an ast allow-list parser, an evaluator and the Excel translation.

Grammar: numbers, sum(<measure>), names of metrics defined earlier, + - * /, unary minus and parentheses.
A division by zero or a blank operand gives blank (None); Excel division is written as IF(den=0,"",num/den).
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal

Op = Literal["+", "-", "*", "/"]


class ExprError(ValueError):
    """An expression outside the allowed grammar, or one that names unknown metrics or measures."""


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Sum:
    measure: str


@dataclass(frozen=True)
class Neg:
    operand: Node


@dataclass(frozen=True)
class Bin:
    op: Op
    left: Node
    right: Node


Node = Num | Ref | Sum | Neg | Bin

_BINARY: dict[type[ast.operator], Op] = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_PRECEDENCE: dict[str, int] = {"+": 1, "-": 1, "*": 2, "/": 2}
_ATOM = 3


def parse(text: str) -> Node:
    """Parse one expression; anything outside the grammar raises ExprError."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"{text!r} is not a valid expression") from exc
    return _convert(tree.body, text)


def _convert(node: ast.expr, text: str) -> Node:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return Num(float(value))
        raise ExprError(f"{text!r}: the constant {value!r} is not allowed")
    if isinstance(node, ast.Name):
        return Ref(node.id)
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "sum"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Name)
        ):
            return Sum(node.args[0].id)
        raise ExprError(f"{text!r}: only sum(<measure>) may be called")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return Neg(_convert(node.operand, text))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return Bin(_BINARY[type(node.op)], _convert(node.left, text), _convert(node.right, text))
    raise ExprError(f"{text!r}: {type(node).__name__} is not allowed")


def _walk(node: Node) -> Iterator[Node]:
    yield node
    if isinstance(node, Neg):
        yield from _walk(node.operand)
    elif isinstance(node, Bin):
        yield from _walk(node.left)
        yield from _walk(node.right)


def references(node: Node) -> set[str]:
    return {item.name for item in _walk(node) if isinstance(item, Ref)}


def measures(node: Node) -> set[str]:
    return {item.measure for item in _walk(node) if isinstance(item, Sum)}


def evaluate(node: Node, sum_of: Callable[[str], float], ref: Callable[[str], float | None]) -> float | None:
    """Value of node; sum_of gives the sum of a measure in the scope, ref the value of an earlier metric."""
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Sum):
        return sum_of(node.measure)
    if isinstance(node, Ref):
        return ref(node.name)
    if isinstance(node, Neg):
        value = evaluate(node.operand, sum_of, ref)
        return None if value is None else -value
    left = evaluate(node.left, sum_of, ref)
    right = evaluate(node.right, sum_of, ref)
    if left is None or right is None:
        return None
    if node.op == "+":
        return left + right
    if node.op == "-":
        return left - right
    if node.op == "*":
        return left * right
    return None if right == 0 else left / right


def _number(value: float) -> str:
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def _wrap(text: str, precedence: int, minimum: int) -> str:
    return text if precedence >= minimum else f"({text})"


def _excel(node: Node, ref: Callable[[str], str], sum_of: Callable[[str], str]) -> tuple[str, int]:
    if isinstance(node, Num):
        return _number(node.value), _ATOM
    if isinstance(node, Ref):
        return ref(node.name), _ATOM
    if isinstance(node, Sum):
        return sum_of(node.measure), _ATOM
    if isinstance(node, Neg):
        text, precedence = _excel(node.operand, ref, sum_of)
        return "-" + _wrap(text, precedence, _ATOM), _ATOM
    left, left_precedence = _excel(node.left, ref, sum_of)
    right, right_precedence = _excel(node.right, ref, sum_of)
    if node.op == "/":
        numerator = _wrap(left, left_precedence, 2)
        denominator = _wrap(right, right_precedence, _ATOM)
        return f'IF({denominator}=0,"",{numerator}/{denominator})', _ATOM
    own = _PRECEDENCE[node.op]
    return f"{_wrap(left, left_precedence, own)}{node.op}{_wrap(right, right_precedence, own + 1)}", own


def to_excel(node: Node, ref: Callable[[str], str], sum_of: Callable[[str], str]) -> str:
    """Excel formula text without the leading '='; the callbacks give the cell text for metrics and sums."""
    return _excel(node, ref, sum_of)[0]


def change_excel(current: str, previous: str, kind: Literal["relative", "points"]) -> str:
    """Week-on-week change of two cells: relative (blank when previous is 0) or points (x 100)."""
    if kind == "relative":
        return f'IF({previous}=0,"",{current}/{previous}-1)'
    return f'IF(OR({current}="",{previous}=""),"",({current}-{previous})*100)'


def compile_metrics(expressions: Mapping[str, str], known_measures: Iterable[str]) -> dict[str, Node]:
    """Parse metric expressions in order: sum() takes a measure, a bare name a metric defined above."""
    allowed = set(known_measures)
    compiled: dict[str, Node] = {}
    for key, text in expressions.items():
        try:
            node = parse(text)
        except ExprError as exc:
            raise ExprError(f"metric {key}: {exc}") from exc
        for measure in sorted(measures(node)):
            if measure not in allowed:
                raise ExprError(
                    f"metric {key}: sum({measure}) names no measure; measures are {', '.join(sorted(allowed))}"
                )
        for name in sorted(references(node)):
            if name in compiled:
                continue
            if name in expressions:
                raise ExprError(f"metric {key}: {name} must be defined above {key} in report.yaml")
            raise ExprError(f"metric {key}: unknown name {name!r}; use sum(<measure>) for measures")
        compiled[key] = node
    return compiled
