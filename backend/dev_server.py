#!/usr/bin/env python3
"""
Local development server for Dashborion backend.

This Flask server wraps the Lambda handlers to enable local development
with hot reload. It converts HTTP requests to Lambda event format.

Usage:
    cd backend
    flask --app dev_server run --reload --port 8080

Or via pnpm from project root:
    pnpm backend:dev
"""

import json
import os
import sys
from functools import wraps

from flask import Flask, request, Response, make_response
from flask_cors import CORS

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables for LocalStack
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')
os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-west-3')
os.environ.setdefault('LOCALSTACK_ENDPOINT', 'http://localhost:4566')
os.environ.setdefault('CONFIG_TABLE_NAME', 'dashborion-local-config')
os.environ.setdefault('STATE_TABLE_NAME', 'dashborion-local-cache')
os.environ.setdefault('TOKENS_TABLE_NAME', 'dashborion-local-tokens')
os.environ.setdefault('DEVICE_CODES_TABLE_NAME', 'dashborion-local-device-codes')
os.environ.setdefault('USERS_TABLE_NAME', 'dashborion-local-users')
os.environ.setdefault('GROUPS_TABLE_NAME', 'dashborion-local-groups')
os.environ.setdefault('PERMISSIONS_TABLE_NAME', 'dashborion-local-permissions')
os.environ.setdefault('AUDIT_TABLE_NAME', 'dashborion-local-audit')

# Import handlers after setting env vars
from handler import lambda_handler

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


class MockLambdaContext:
    """Mock Lambda context for local development."""
    function_name = "dashborion-local"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:eu-west-3:000000000000:function:dashborion-local"
    memory_limit_in_mb = 256
    aws_request_id = "local-request-id"
    log_group_name = "/aws/lambda/dashborion-local"
    log_stream_name = "local-stream"

    def get_remaining_time_in_millis(self):
        return 300000  # 5 minutes


def flask_to_lambda_event(flask_request):
    """Convert Flask request to Lambda API Gateway v2 event format."""
    # Parse headers (lowercase for API Gateway v2)
    headers = {k.lower(): v for k, v in flask_request.headers.items()}

    # Build event
    event = {
        'version': '2.0',
        'routeKey': f'{flask_request.method} {flask_request.path}',
        'rawPath': flask_request.path,
        'rawQueryString': flask_request.query_string.decode('utf-8'),
        'headers': headers,
        'queryStringParameters': dict(flask_request.args) if flask_request.args else None,
        'requestContext': {
            'http': {
                'method': flask_request.method,
                'path': flask_request.path,
                'protocol': 'HTTP/1.1',
                'sourceIp': flask_request.remote_addr,
                'userAgent': flask_request.user_agent.string
            },
            'requestId': 'local-request',
            'stage': 'local',
            'time': '',
            'timeEpoch': 0
        },
        'isBase64Encoded': False
    }

    # Add body for POST/PUT/PATCH
    if flask_request.method in ['POST', 'PUT', 'PATCH']:
        body = flask_request.get_data(as_text=True)
        event['body'] = body

    return event


def lambda_response_to_flask(lambda_response):
    """Convert Lambda response to Flask response."""
    status_code = lambda_response.get('statusCode', 200)
    headers = lambda_response.get('headers', {})
    body = lambda_response.get('body', '')

    # Create Flask response
    response = make_response(body, status_code)

    # Set headers
    for key, value in headers.items():
        response.headers[key] = value

    return response


@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def api_handler(path):
    """Handle all /api/* routes."""
    # Convert to Lambda event
    event = flask_to_lambda_event(request)
    context = MockLambdaContext()

    # Handle OPTIONS locally for faster CORS
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-SSO-User-Email'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,PATCH,OPTIONS'
        return response

    try:
        # Call Lambda handler
        lambda_response = lambda_handler(event, context)
        return lambda_response_to_flask(lambda_response)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return make_response(json.dumps({'error': str(e)}), 500)


@app.route('/')
def root():
    """Root endpoint - redirect to health."""
    return {'message': 'Dashborion API - Local Development', 'health': '/api/health'}


if __name__ == '__main__':
    print("=" * 60)
    print("Dashborion Backend - Local Development Server")
    print("=" * 60)
    print(f"LocalStack endpoint: {os.environ.get('LOCALSTACK_ENDPOINT')}")
    print(f"Config table: {os.environ.get('CONFIG_TABLE_NAME')}")
    print("")
    print("Starting Flask server on http://localhost:8080")
    print("Hot reload enabled - changes will auto-reload")
    print("=" * 60)

    app.run(host='0.0.0.0', port=8080, debug=True)
