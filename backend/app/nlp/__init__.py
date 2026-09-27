"""NLP semantic change analysis (docs/06_NLP_SPEC.md). Advisory only: never alters the
verification verdict.
"""

from app.nlp.classifier import ChangeClassifier, RuleOnlyClassifier
from app.nlp.types import Category, ChangeAnalysis, DiffOp, EntityChange

__all__ = [
    "Category",
    "ChangeAnalysis",
    "ChangeClassifier",
    "DiffOp",
    "EntityChange",
    "RuleOnlyClassifier",
]
