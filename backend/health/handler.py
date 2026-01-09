"""
Health Check Lambda Handler.

Provides a simple health check endpoint that does not require authentication.
Used for load balancer health checks and service monitoring.
"""

import json
import time
from typing import Dict, Any


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Health check handler.

    GET /api/health

    Returns basic service health information.
    """
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps({
            'status': 'healthy',
            'service': 'dashborion-api',
            'timestamp': int(time.time()),
        })
    }
