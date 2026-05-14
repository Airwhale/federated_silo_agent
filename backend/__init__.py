"""Backend package for the federated AML agent runtime."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent

__all__ = ["BACKEND_ROOT"]
