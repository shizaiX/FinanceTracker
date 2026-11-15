"""Stickman Tournament Universe — procedural stickman tournament video engine."""
import os

__version__ = "0.1.0"

#: Project root (folder containing config.yaml, themes/, library/, ...).
PROJECT_ROOT = os.environ.get(
    "STU_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
