"""
Re-export lambda handler from backend module.
This file exists at root for SST handler discovery.
"""

import sys
import os

# Add backend directory to Python path for relative imports within backend/
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Now import the actual handler (this will find config, utils, providers correctly)
from backend.handler import lambda_handler

__all__ = ["lambda_handler"]
