# Re-export lambda handler from backend module
# This file exists at root for SST handler discovery
from backend.handler import lambda_handler

__all__ = ["lambda_handler"]
