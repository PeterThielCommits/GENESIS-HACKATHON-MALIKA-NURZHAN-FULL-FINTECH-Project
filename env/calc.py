"""Safe AST-only exact Decimal calculator tool (REQ-ENV-020..023).

Never calls ``eval`` or ``exec``. Rejects oversized expressions, oversized ASTs,
attribute access, subscripts, imports, power bombs, division by zero, and
non-finite results with bounded ``EnvError("CALC_ERROR", ...)``.
"""

from __future__ import annotations

import ast
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from typing import Any

from env.errors import EnvError

CALC_PRECISION = 50
MAX_RESULT_DIGITS = 80


def _round_dec(value: Decimal, places: Decimal, mode: str) -> Decimal:
    if places != int(places):
        raise EnvError("CALC_ERROR", "rounding places must be an integer")
    p = int(places)
    if not -20 <= p <= 20:
        raise EnvError("CALC_ERROR", "rounding places out of range [-20, 20]")
    quant = Decimal(1).scaleb(-p)
    rounding = ROUND_HALF_EVEN if mode == "half_even" else ROUND_HALF_UP
    with localcontext(Context(prec=CALC_PRECISION, rounding=rounding)):
        return value.quantize(quant)


def _eval_node(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise EnvError("CALC_ERROR", "boolean literals are forbidden")
        if isinstance(node.value, int):
            return Decimal(node.value)
        if isinstance(node.value, float):
            # Parse from repr to avoid binary noise as much as possible, still exact Decimal
            try:
                d = Decimal(str(node.value))
            except InvalidOperation as exc:
                raise EnvError("CALC_ERROR", "invalid numeric literal") from exc
            if not d.is_finite():
                raise EnvError("CALC_ERROR", "non-finite literal")
            return d
        raise EnvError("CALC_ERROR", f"unsupported literal type: {type(node.value).__name__}")

    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise EnvError("CALC_ERROR", f"unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        with localcontext(Context(prec=CALC_PRECISION)):
            if isinstance(node.op, ast.Add):
                res = left + right
            elif isinstance(node.op, ast.Sub):
                res = left - right
            elif isinstance(node.op, ast.Mult):
                res = left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    raise EnvError("CALC_ERROR", "division by zero")
                res = left / right
            else:
                raise EnvError("CALC_ERROR", f"unsupported binary operator: {type(node.op).__name__}")
        if not res.is_finite():
            raise EnvError("CALC_ERROR", "non-finite arithmetic result")
        return res

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise EnvError("CALC_ERROR", "only positional calls to whitelisted functions are allowed")
        fn = node.func.id
        args = [_eval_node(a) for a in node.args]
        if fn == "abs" and len(args) == 1:
            return abs(args[0])
        if fn == "min" and len(args) >= 1:
            return min(args)
        if fn == "max" and len(args) >= 1:
            return max(args)
        if fn == "round_half_even" and len(args) in (1, 2):
            return _round_dec(args[0], args[1] if len(args) == 2 else Decimal(0), "half_even")
        if fn == "round_half_up" and len(args) in (1, 2):
            return _round_dec(args[0], args[1] if len(args) == 2 else Decimal(0), "half_up")
        raise EnvError("CALC_ERROR", f"disallowed function or wrong arity: {fn}")

    raise EnvError("CALC_ERROR", f"disallowed expression construct: {type(node).__name__}")


def _format_decimal(value: Decimal) -> str:
    norm = value.normalize()
    text = format(norm, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    if len(text) > MAX_RESULT_DIGITS:
        raise EnvError("CALC_ERROR", "result exceeds maximum digit bound")
    return text


def evaluate_calc(
    expression: Any,
    *,
    max_length: int = 500,
    max_ast_nodes: int = 100,
) -> dict[str, str]:
    """Safely evaluate a decimal arithmetic expression and return exact string result."""
    if not isinstance(expression, str) or not expression.strip():
        raise EnvError("CALC_ERROR", "expression must be a non-empty string")
    if len(expression) > max_length:
        raise EnvError("CALC_ERROR", f"expression exceeds max length ({max_length})")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise EnvError("CALC_ERROR", f"syntax error: {exc.msg}") from exc

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > max_ast_nodes:
        raise EnvError("CALC_ERROR", f"expression exceeds max AST nodes ({max_ast_nodes})")

    try:
        value = _eval_node(tree)
    except EnvError:
        raise
    except (ArithmeticError, ValueError, OverflowError) as exc:
        raise EnvError("CALC_ERROR", f"arithmetic failure: {exc}") from exc

    return {"result": _format_decimal(value)}


__all__ = ["evaluate_calc"]
