"""Deterministic tools for the runtime benchmark agent (no raw eval, read-only lookup)."""

from __future__ import annotations

import ast
import operator
from typing import Any, Dict

# Supported operators for safe AST calculator
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Pow: operator.pow,
}

# Deterministic Knowledge Fixture Table for Lookup Tool
FIXTURE_DATABASE = {
    "account:101": {
        "account_id": "101",
        "name": "Acme Corp",
        "tier": "enterprise",
        "monthly_quota": 1000000,
        "status": "active",
    },
    "account:102": {
        "account_id": "102",
        "name": "Beta Labs",
        "tier": "standard",
        "monthly_quota": 50000,
        "status": "active",
    },
    "account:103": {
        "account_id": "103",
        "name": "Gamma Dev",
        "tier": "starter",
        "monthly_quota": 10000,
        "status": "suspended",
    },
    "service:gateway": {
        "service": "gateway",
        "version": "0.1.0",
        "port": 8000,
        "protocol": "HTTP/REST",
        "maintainer": "core-infra",
    },
    "pricing:mock-cheap": {"model": "mock-cheap", "input_per_1m": 0.15, "output_per_1m": 0.60, "tier": "cheap"},
    "pricing:mock-strong": {"model": "mock-strong", "input_per_1m": 2.50, "output_per_1m": 10.00, "tier": "strong"},
    "server:us-east-1": {
        "datacenter": "us-east-1",
        "capacity_units": 450,
        "utilization_pct": 74.2,
        "status": "operational",
    },
    "server:eu-west-1": {
        "datacenter": "eu-west-1",
        "capacity_units": 320,
        "utilization_pct": 88.5,
        "status": "operational",
    },
}


class CalculatorTool:
    """Safe deterministic arithmetic tool using AST parsing."""

    name = "calculator"

    @classmethod
    def execute(cls, expression: str) -> Dict[str, Any]:
        """Safely evaluate arithmetic expression without using eval()."""
        try:
            expr_str = expression.strip().replace("^", "**")
            if len(expr_str) > 100:
                return {"ok": False, "error": "Expression exceeds maximum length of 100 characters"}

            tree = ast.parse(expr_str, mode="eval")
            result = cls._eval_node(tree.body)
            # Round float values for stable precision
            if isinstance(result, float):
                result = round(result, 6)
            return {"ok": True, "result": result, "error": None}
        except ZeroDivisionError:
            return {"ok": False, "error": "Division by zero", "result": None}
        except Exception as e:
            return {"ok": False, "error": f"Invalid expression: {type(e).__name__}", "result": None}

    @classmethod
    def _eval_node(cls, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            return SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            operand = cls._eval_node(node.operand)
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Disallowed expression node: {type(node).__name__}")


class LookupTool:
    """Controlled read-only fixture table lookup tool."""

    name = "lookup"

    @classmethod
    def execute(cls, record_key: str) -> Dict[str, Any]:
        """Lookup record by key from local fixture database."""
        key = record_key.strip().lower()
        if not key or len(key) > 64:
            return {"ok": False, "error": "Invalid record key", "record": None}

        record = FIXTURE_DATABASE.get(key)
        if record:
            return {"ok": True, "record": record, "error": None}
        return {"ok": False, "error": f"Record '{key}' not found", "record": None}
