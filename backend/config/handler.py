"""
Config Registry Lambda Handler.

Handles all config registry endpoints:
- Global settings (features, comparison groups, opsIntegration)
- Projects (CRUD)
- Environments (CRUD)
- Clusters (CRUD)
- AWS Accounts (CRUD)
- Export/Import/Validation
- Resolution (for terraform-aws-ops)

All endpoints require global admin access.
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

from shared.rbac import get_auth_context, is_global_admin
from shared.response import (
    json_response,
    error_response,
    get_method,
    get_path,
    get_body,
)

# Table name from environment
CONFIG_TABLE = os.environ.get('CONFIG_TABLE_NAME', 'dashborion-config')

# DynamoDB client (lazy init)
_dynamodb = None


def _get_dynamodb():
    """Get DynamoDB resource (lazy init)."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def _get_table():
    """Get the config table."""
    return _get_dynamodb().Table(CONFIG_TABLE)


def _now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + 'Z'


def _decimal_to_native(obj):
    """Convert Decimal to int/float for JSON serialization."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    return obj


# =============================================================================
# Main Handler
# =============================================================================

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for config registry endpoints."""
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # /api/config/full is accessible to all authenticated users (used by frontend)
    if path == '/api/config/full' and method == 'GET':
        try:
            return get_frontend_config()
        except Exception as e:
            print(f"Error in get_frontend_config: {e}")
            return error_response('internal_error', str(e), 500)

    # All other config endpoints require global admin
    if not is_global_admin(auth):
        return error_response('forbidden', 'Global admin access required', 403)

    # Get actor email
    actor_email = auth.email if auth else 'unknown'

    # Parse body and path params
    body = get_body(event)
    path_params = event.get('pathParameters') or {}

    try:
        return route_request(path, method, body, path_params, actor_email)
    except Exception as e:
        print(f"Error in config handler: {e}")
        return error_response('internal_error', str(e), 500)


def route_request(path: str, method: str, body: Dict, path_params: Dict, actor: str) -> Dict:
    """Route request to appropriate handler."""

    # Settings
    if path == '/api/config/settings':
        if method == 'GET':
            return get_settings()
        elif method == 'PUT':
            return update_settings(body, actor)

    # Projects
    if path == '/api/config/projects':
        if method == 'GET':
            return list_projects()
        elif method == 'POST':
            return create_project(body, actor)

    if re.match(r'^/api/config/projects/[^/]+$', path):
        project_id = path_params.get('projectId')
        if method == 'GET':
            return get_project(project_id)
        elif method == 'PUT':
            return update_project(project_id, body, actor)
        elif method == 'DELETE':
            return delete_project(project_id, actor)

    # Environments
    if re.match(r'^/api/config/projects/[^/]+/environments$', path):
        project_id = path_params.get('projectId')
        if method == 'GET':
            return list_environments(project_id)
        elif method == 'POST':
            return create_environment(project_id, body, actor)

    if re.match(r'^/api/config/projects/[^/]+/environments/[^/]+$', path):
        project_id = path_params.get('projectId')
        env_id = path_params.get('envId')
        if method == 'GET':
            return get_environment(project_id, env_id)
        elif method == 'PUT':
            return update_environment(project_id, env_id, body, actor)
        elif method == 'DELETE':
            return delete_environment(project_id, env_id, actor)

    if re.match(r'^/api/config/projects/[^/]+/environments/[^/]+/checkers$', path):
        project_id = path_params.get('projectId')
        env_id = path_params.get('envId')
        if method == 'PATCH':
            return update_environment_checkers(project_id, env_id, body, actor)

    # Clusters
    if path == '/api/config/clusters':
        if method == 'GET':
            return list_clusters()
        elif method == 'POST':
            return create_cluster(body, actor)

    if re.match(r'^/api/config/clusters/[^/]+$', path):
        cluster_id = path_params.get('clusterId')
        if method == 'GET':
            return get_cluster(cluster_id)
        elif method == 'PUT':
            return update_cluster(cluster_id, body, actor)
        elif method == 'DELETE':
            return delete_cluster(cluster_id, actor)

    # AWS Accounts
    if path == '/api/config/aws-accounts':
        if method == 'GET':
            return list_aws_accounts()
        elif method == 'POST':
            return create_aws_account(body, actor)

    if re.match(r'^/api/config/aws-accounts/[^/]+$', path):
        account_id = path_params.get('accountId')
        if method == 'GET':
            return get_aws_account(account_id)
        elif method == 'PUT':
            return update_aws_account(account_id, body, actor)
        elif method == 'DELETE':
            return delete_aws_account(account_id, actor)

    # CI Providers (Jenkins, ArgoCD, etc.)
    if path == '/api/config/ci-providers':
        if method == 'GET':
            return list_ci_providers()
        elif method == 'POST':
            return create_ci_provider(body, actor)

    # Test CI Provider connection (without saving) - must be before /{providerId}/test
    if path == '/api/config/ci-providers/test':
        if method == 'POST':
            return test_ci_provider_credentials(body)

    if re.match(r'^/api/config/ci-providers/[^/]+/test$', path):
        provider_id = path_params.get('providerId')
        if method == 'POST':
            return test_ci_provider(provider_id)

    if re.match(r'^/api/config/ci-providers/[^/]+$', path):
        provider_id = path_params.get('providerId')
        if method == 'GET':
            return get_ci_provider(provider_id)
        elif method == 'PUT':
            return update_ci_provider(provider_id, body, actor)
        elif method == 'DELETE':
            return delete_ci_provider(provider_id, actor)

    # Export/Import/Validation
    if path == '/api/config/export' and method == 'GET':
        return export_config()
    if path == '/api/config/import' and method == 'POST':
        return import_config(body, actor)
    if path == '/api/config/validate' and method == 'POST':
        return validate_config(body)
    if path == '/api/config/migrate-from-json' and method == 'POST':
        return migrate_from_json(body, actor)

    # Resolution (for terraform-aws-ops)
    if re.match(r'^/api/config/resolve/[^/]+/[^/]+$', path):
        project_id = path_params.get('projectId')
        env_id = path_params.get('envId')
        if method == 'GET':
            return resolve_config(project_id, env_id)

    # Secrets Management (for CI/CD provider tokens)
    # Handle special routes first
    if path == '/api/config/secrets/test-connection' and method == 'POST':
        return test_provider_connection(body)

    if path == '/api/config/secrets/discover' and method == 'POST':
        return discover_pipelines(body)

    # Generic secret CRUD routes
    secrets_match = re.match(r'^/api/config/secrets/([^/]+)$', path)
    if secrets_match:
        secret_type = secrets_match.group(1)
        if method == 'POST':
            return create_or_update_secret(secret_type, body, actor)
        elif method == 'DELETE':
            return delete_secret(secret_type, body, actor)
        elif method == 'GET':
            return get_secret_info(secret_type, body)

    return error_response('not_found', f'Unknown endpoint: {method} {path}', 404)


# =============================================================================
# Settings
# =============================================================================

def get_settings() -> Dict:
    """Get global settings."""
    table = _get_table()
    response = table.get_item(Key={'pk': 'GLOBAL', 'sk': 'settings'})
    item = response.get('Item')
    if not item:
        # Return default settings
        return json_response(200, {
            'features': {},
            'comparison': {},
            'opsIntegration': {},
            'secretsPrefix': '/dashborion',
        })
    # Ensure secretsPrefix has a default
    item = _decimal_to_native(item)
    if 'secretsPrefix' not in item:
        item['secretsPrefix'] = '/dashborion'
    return json_response(200, item)


def update_settings(body: Dict, actor: str) -> Dict:
    """Update global settings."""
    table = _get_table()
    now = _now_iso()

    # Get existing to increment version
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': 'settings'}).get('Item', {})
    version = existing.get('version', 0) + 1

    item = {
        'pk': 'GLOBAL',
        'sk': 'settings',
        'features': body.get('features', existing.get('features', {})),
        'comparison': body.get('comparison', existing.get('comparison', {})),
        'opsIntegration': body.get('opsIntegration', existing.get('opsIntegration', {})),
        'secretsPrefix': body.get('secretsPrefix', existing.get('secretsPrefix', '/dashborion')),
        'updatedAt': now,
        'updatedBy': actor,
        'version': version,
    }
    table.put_item(Item=item)
    return json_response(200, _decimal_to_native(item))


# =============================================================================
# Projects
# =============================================================================

def list_projects() -> Dict:
    """List all projects with environment counts."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('PROJECT')
    )
    projects = [_decimal_to_native(item) for item in response.get('Items', [])]

    # Count environments for each project
    env_response = table.query(
        KeyConditionExpression=Key('pk').eq('ENV')
    )
    env_items = env_response.get('Items', [])

    # Build count map: projectId -> count
    env_counts = {}
    for env in env_items:
        project_id = env.get('projectId')
        if project_id:
            env_counts[project_id] = env_counts.get(project_id, 0) + 1

    # Add environmentCount to each project
    for project in projects:
        project_id = project.get('projectId')
        project['environmentCount'] = env_counts.get(project_id, 0)

    return json_response(200, {'projects': projects})


def get_project(project_id: str) -> Dict:
    """Get a specific project."""
    table = _get_table()
    response = table.get_item(Key={'pk': 'PROJECT', 'sk': project_id})
    item = response.get('Item')
    if not item:
        return error_response('not_found', f'Project {project_id} not found', 404)
    return json_response(200, _decimal_to_native(item))


def create_project(body: Dict, actor: str) -> Dict:
    """Create a new project."""
    project_id = body.get('projectId')
    if not project_id:
        return error_response('validation', 'projectId is required', 400)

    table = _get_table()
    now = _now_iso()

    # Check if exists
    existing = table.get_item(Key={'pk': 'PROJECT', 'sk': project_id}).get('Item')
    if existing:
        return error_response('conflict', f'Project {project_id} already exists', 409)

    item = {
        'pk': 'PROJECT',
        'sk': project_id,
        'projectId': project_id,
        'displayName': body.get('displayName', project_id),
        'description': body.get('description', ''),
        'status': body.get('status', 'active'),
        'orchestratorType': body.get('orchestratorType', ''),  # eks, ecs, or empty
        'idpGroupMapping': body.get('idpGroupMapping', {}),
        'features': body.get('features', {}),
        'pipelines': body.get('pipelines', {}),
        'topology': body.get('topology', {}),
        'serviceNaming': body.get('serviceNaming', {}),
        'updatedAt': now,
        'updatedBy': actor,
        'version': 1,
    }
    table.put_item(Item=item)
    return json_response(201, _decimal_to_native(item))


def update_project(project_id: str, body: Dict, actor: str) -> Dict:
    """Update a project."""
    table = _get_table()
    now = _now_iso()

    # Get existing
    existing = table.get_item(Key={'pk': 'PROJECT', 'sk': project_id}).get('Item')
    if not existing:
        return error_response('not_found', f'Project {project_id} not found', 404)

    version = existing.get('version', 0) + 1

    item = {
        'pk': 'PROJECT',
        'sk': project_id,
        'projectId': project_id,
        'displayName': body.get('displayName', existing.get('displayName')),
        'description': body.get('description', existing.get('description', '')),
        'status': body.get('status', existing.get('status')),
        'orchestratorType': body.get('orchestratorType', existing.get('orchestratorType', '')),
        'idpGroupMapping': body.get('idpGroupMapping', existing.get('idpGroupMapping', {})),
        'features': body.get('features', existing.get('features', {})),
        'pipelines': body.get('pipelines', existing.get('pipelines', {})),
        'topology': body.get('topology', existing.get('topology', {})),
        'serviceNaming': body.get('serviceNaming', existing.get('serviceNaming', {})),
        'updatedAt': now,
        'updatedBy': actor,
        'version': version,
    }
    table.put_item(Item=item)
    return json_response(200, _decimal_to_native(item))


def delete_project(project_id: str, actor: str) -> Dict:
    """Delete a project and all its environments."""
    table = _get_table()

    # Check if exists
    existing = table.get_item(Key={'pk': 'PROJECT', 'sk': project_id}).get('Item')
    if not existing:
        return error_response('not_found', f'Project {project_id} not found', 404)

    # Delete all environments first
    env_response = table.query(
        KeyConditionExpression=Key('pk').eq('ENV') & Key('sk').begins_with(f'{project_id}#')
    )
    for env in env_response.get('Items', []):
        table.delete_item(Key={'pk': 'ENV', 'sk': env['sk']})

    # Delete project
    table.delete_item(Key={'pk': 'PROJECT', 'sk': project_id})

    return json_response(200, {'deleted': project_id, 'deletedBy': actor})


# =============================================================================
# Environments
# =============================================================================

def list_environments(project_id: str) -> Dict:
    """List environments for a project."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('ENV') & Key('sk').begins_with(f'{project_id}#')
    )
    items = [_decimal_to_native(item) for item in response.get('Items', [])]
    return json_response(200, {'environments': items})


def get_environment(project_id: str, env_id: str) -> Dict:
    """Get a specific environment."""
    table = _get_table()
    sk = f'{project_id}#{env_id}'
    response = table.get_item(Key={'pk': 'ENV', 'sk': sk})
    item = response.get('Item')
    if not item:
        return error_response('not_found', f'Environment {env_id} not found in project {project_id}', 404)
    return json_response(200, _decimal_to_native(item))


def create_environment(project_id: str, body: Dict, actor: str) -> Dict:
    """Create a new environment."""
    env_id = body.get('envId')
    if not env_id:
        return error_response('validation', 'envId is required', 400)

    table = _get_table()
    now = _now_iso()
    sk = f'{project_id}#{env_id}'

    # Check if exists
    existing = table.get_item(Key={'pk': 'ENV', 'sk': sk}).get('Item')
    if existing:
        return error_response('conflict', f'Environment {env_id} already exists in project {project_id}', 409)

    item = {
        'pk': 'ENV',
        'sk': sk,
        'projectId': project_id,
        'envId': env_id,
        'displayName': body.get('displayName', env_id),
        'accountId': body.get('accountId', ''),
        'region': body.get('region', 'eu-central-1'),
        'clusterName': body.get('clusterName', ''),
        'namespace': body.get('namespace', ''),
        'services': body.get('services', []),
        'readRoleArn': body.get('readRoleArn'),
        'actionRoleArn': body.get('actionRoleArn'),
        'status': body.get('status', 'planned'),
        'enabled': body.get('enabled', True),
        'checkers': body.get('checkers', {}),
        'infrastructure': body.get('infrastructure', {}),
        'topology': body.get('topology', {}),
        'updatedAt': now,
        'updatedBy': actor,
        'version': 1,
    }
    table.put_item(Item=item)
    return json_response(201, _decimal_to_native(item))


def update_environment(project_id: str, env_id: str, body: Dict, actor: str) -> Dict:
    """Update an environment."""
    table = _get_table()
    now = _now_iso()
    sk = f'{project_id}#{env_id}'

    # Get existing
    existing = table.get_item(Key={'pk': 'ENV', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'Environment {env_id} not found in project {project_id}', 404)

    version = existing.get('version', 0) + 1

    item = {
        'pk': 'ENV',
        'sk': sk,
        'projectId': project_id,
        'envId': env_id,
        'displayName': body.get('displayName', existing.get('displayName')),
        'accountId': body.get('accountId', existing.get('accountId', '')),
        'region': body.get('region', existing.get('region', 'eu-central-1')),
        'clusterName': body.get('clusterName', existing.get('clusterName', '')),
        'namespace': body.get('namespace', existing.get('namespace', '')),
        'services': body.get('services', existing.get('services', [])),
        'readRoleArn': body.get('readRoleArn', existing.get('readRoleArn')),
        'actionRoleArn': body.get('actionRoleArn', existing.get('actionRoleArn')),
        'status': body.get('status', existing.get('status')),
        'enabled': body.get('enabled', existing.get('enabled', True)),
        'checkers': body.get('checkers', existing.get('checkers', {})),
        'infrastructure': body.get('infrastructure', existing.get('infrastructure', {})),
        'topology': body.get('topology', existing.get('topology', {})),
        'updatedAt': now,
        'updatedBy': actor,
        'version': version,
    }
    table.put_item(Item=item)
    return json_response(200, _decimal_to_native(item))


def delete_environment(project_id: str, env_id: str, actor: str) -> Dict:
    """Delete an environment."""
    table = _get_table()
    sk = f'{project_id}#{env_id}'

    # Check if exists
    existing = table.get_item(Key={'pk': 'ENV', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'Environment {env_id} not found in project {project_id}', 404)

    table.delete_item(Key={'pk': 'ENV', 'sk': sk})
    return json_response(200, {'deleted': f'{project_id}/{env_id}', 'deletedBy': actor})


def update_environment_checkers(project_id: str, env_id: str, body: Dict, actor: str) -> Dict:
    """Update only the checkers config of an environment (PATCH)."""
    table = _get_table()
    now = _now_iso()
    sk = f'{project_id}#{env_id}'

    # Get existing
    existing = table.get_item(Key={'pk': 'ENV', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'Environment {env_id} not found in project {project_id}', 404)

    version = existing.get('version', 0) + 1

    # Merge checkers
    checkers = existing.get('checkers', {})
    checkers.update(body.get('checkers', body))

    table.update_item(
        Key={'pk': 'ENV', 'sk': sk},
        UpdateExpression='SET checkers = :c, updatedAt = :u, updatedBy = :a, version = :v',
        ExpressionAttributeValues={
            ':c': checkers,
            ':u': now,
            ':a': actor,
            ':v': version,
        }
    )
    return json_response(200, {'projectId': project_id, 'envId': env_id, 'checkers': checkers})


# =============================================================================
# Clusters
# =============================================================================

def list_clusters() -> Dict:
    """List all clusters."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('GLOBAL') & Key('sk').begins_with('cluster:')
    )
    items = [_decimal_to_native(item) for item in response.get('Items', [])]
    return json_response(200, {'clusters': items})


def get_cluster(cluster_id: str) -> Dict:
    """Get a specific cluster."""
    table = _get_table()
    sk = f'cluster:{cluster_id}'
    response = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk})
    item = response.get('Item')
    if not item:
        return error_response('not_found', f'Cluster {cluster_id} not found', 404)
    return json_response(200, _decimal_to_native(item))


def create_cluster(body: Dict, actor: str) -> Dict:
    """Create a new cluster."""
    cluster_id = body.get('clusterId')
    if not cluster_id:
        return error_response('validation', 'clusterId is required', 400)

    table = _get_table()
    now = _now_iso()
    sk = f'cluster:{cluster_id}'

    account_id = body.get('awsAccountId') or body.get('accountId', '')
    cluster_name = body.get('clusterName') or body.get('name', cluster_id)

    # Check if exists
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if existing:
        return error_response('conflict', f'Cluster {cluster_id} already exists', 409)

    item = {
        'pk': 'GLOBAL',
        'sk': sk,
        'clusterId': cluster_id,
        'name': cluster_name,
        'clusterName': cluster_name,
        'displayName': body.get('displayName', cluster_id),
        'region': body.get('region', 'eu-central-1'),
        'accountId': account_id,
        'awsAccountId': account_id,
        'type': body.get('type', ''),
        'version': body.get('version', ''),
        'updatedAt': now,
        'updatedBy': actor,
    }
    table.put_item(Item=item)
    return json_response(201, _decimal_to_native(item))


def update_cluster(cluster_id: str, body: Dict, actor: str) -> Dict:
    """Update a cluster."""
    table = _get_table()
    now = _now_iso()
    sk = f'cluster:{cluster_id}'

    # Get existing
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'Cluster {cluster_id} not found', 404)

    account_id = body.get('awsAccountId') or body.get('accountId', existing.get('accountId', ''))
    cluster_name = body.get('clusterName') or body.get('name', existing.get('name', cluster_id))

    item = {
        'pk': 'GLOBAL',
        'sk': sk,
        'clusterId': cluster_id,
        'name': cluster_name,
        'clusterName': cluster_name,
        'displayName': body.get('displayName', existing.get('displayName')),
        'region': body.get('region', existing.get('region', 'eu-central-1')),
        'accountId': account_id,
        'awsAccountId': account_id,
        'type': body.get('type', existing.get('type', '')),
        'version': body.get('version', existing.get('version', '')),
        'updatedAt': now,
        'updatedBy': actor,
    }
    table.put_item(Item=item)
    return json_response(200, _decimal_to_native(item))


def delete_cluster(cluster_id: str, actor: str) -> Dict:
    """Delete a cluster."""
    table = _get_table()
    sk = f'cluster:{cluster_id}'

    # Check if exists
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'Cluster {cluster_id} not found', 404)

    table.delete_item(Key={'pk': 'GLOBAL', 'sk': sk})
    return json_response(200, {'deleted': cluster_id, 'deletedBy': actor})


# =============================================================================
# AWS Accounts
# =============================================================================

def list_aws_accounts() -> Dict:
    """List all AWS accounts."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('GLOBAL') & Key('sk').begins_with('aws-account:')
    )
    items = [_decimal_to_native(item) for item in response.get('Items', [])]
    return json_response(200, {'awsAccounts': items})


def get_aws_account(account_id: str) -> Dict:
    """Get a specific AWS account."""
    table = _get_table()
    sk = f'aws-account:{account_id}'
    response = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk})
    item = response.get('Item')
    if not item:
        return error_response('not_found', f'AWS Account {account_id} not found', 404)
    return json_response(200, _decimal_to_native(item))


def create_aws_account(body: Dict, actor: str) -> Dict:
    """Create a new AWS account."""
    account_id = body.get('accountId')
    if not account_id:
        return error_response('validation', 'accountId is required', 400)

    table = _get_table()
    now = _now_iso()
    sk = f'aws-account:{account_id}'

    # Check if exists
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if existing:
        return error_response('conflict', f'AWS Account {account_id} already exists', 409)

    item = {
        'pk': 'GLOBAL',
        'sk': sk,
        'accountId': account_id,
        'displayName': body.get('displayName', account_id),
        'readRoleArn': body.get('readRoleArn', ''),
        'actionRoleArn': body.get('actionRoleArn', ''),
        'defaultRegion': body.get('defaultRegion', 'eu-central-1'),
        'updatedAt': now,
        'updatedBy': actor,
    }
    table.put_item(Item=item)
    return json_response(201, _decimal_to_native(item))


def update_aws_account(account_id: str, body: Dict, actor: str) -> Dict:
    """Update an AWS account."""
    table = _get_table()
    now = _now_iso()
    sk = f'aws-account:{account_id}'

    # Get existing
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'AWS Account {account_id} not found', 404)

    item = {
        'pk': 'GLOBAL',
        'sk': sk,
        'accountId': account_id,
        'displayName': body.get('displayName', existing.get('displayName')),
        'readRoleArn': body.get('readRoleArn', existing.get('readRoleArn', '')),
        'actionRoleArn': body.get('actionRoleArn', existing.get('actionRoleArn', '')),
        'defaultRegion': body.get('defaultRegion', existing.get('defaultRegion', 'eu-central-1')),
        'updatedAt': now,
        'updatedBy': actor,
    }
    table.put_item(Item=item)
    return json_response(200, _decimal_to_native(item))


def delete_aws_account(account_id: str, actor: str) -> Dict:
    """Delete an AWS account."""
    table = _get_table()
    sk = f'aws-account:{account_id}'

    # Check if exists
    existing = table.get_item(Key={'pk': 'GLOBAL', 'sk': sk}).get('Item')
    if not existing:
        return error_response('not_found', f'AWS Account {account_id} not found', 404)

    table.delete_item(Key={'pk': 'GLOBAL', 'sk': sk})
    return json_response(200, {'deleted': account_id, 'deletedBy': actor})


# =============================================================================
# CI Providers (Jenkins, ArgoCD, etc.)
# =============================================================================

# Valid CI provider types
CI_PROVIDER_TYPES = ['jenkins', 'argocd', 'codepipeline', 'github-actions', 'azure-devops']


def list_ci_providers() -> Dict:
    """List all CI providers."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('CI_PROVIDER')
    )
    items = [_decimal_to_native(item) for item in response.get('Items', [])]
    # Remove token from response (security)
    for item in items:
        item.pop('token', None)
    return json_response(200, {'ciProviders': items})


def get_ci_provider(provider_id: str) -> Dict:
    """Get a specific CI provider (without token)."""
    table = _get_table()
    response = table.get_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id})
    item = response.get('Item')
    if not item:
        return error_response('not_found', f'CI Provider {provider_id} not found', 404)
    # Remove token from response (security)
    item = _decimal_to_native(item)
    item.pop('token', None)
    return json_response(200, item)


def get_ci_provider_with_credentials(provider_id: str) -> Optional[Dict]:
    """
    Get CI provider with credentials (internal use only).
    Loads token from Secrets Manager if tokenSecret is specified.
    """
    table = _get_table()
    response = table.get_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id})
    item = response.get('Item')
    if not item:
        return None

    item = _decimal_to_native(item)

    # If tokenSecret is specified, load from Secrets Manager
    token_secret = item.get('tokenSecret')
    if token_secret and not item.get('token'):
        try:
            client = _get_secretsmanager_client()
            response = client.get_secret_value(SecretId=token_secret)
            secret_data = json.loads(response['SecretString'])
            item['token'] = secret_data.get('token', secret_data.get('api_token', ''))
            # Also get url/user from secret if not in DynamoDB item
            if not item.get('url'):
                item['url'] = secret_data.get('url', '')
            if not item.get('user'):
                item['user'] = secret_data.get('user', '')
        except Exception as e:
            print(f"Error loading token from Secrets Manager {token_secret}: {e}")

    return item


def create_ci_provider(body: Dict, actor: str) -> Dict:
    """Create a new CI provider."""
    provider_id = body.get('providerId')
    provider_type = body.get('type')

    if not provider_id:
        return error_response('validation', 'providerId is required', 400)
    if not provider_type:
        return error_response('validation', 'type is required', 400)
    if provider_type not in CI_PROVIDER_TYPES:
        return error_response('validation', f'Invalid type. Must be one of: {", ".join(CI_PROVIDER_TYPES)}', 400)

    table = _get_table()
    now = _now_iso()

    # Check if exists
    existing = table.get_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id}).get('Item')
    if existing:
        return error_response('conflict', f'CI Provider {provider_id} already exists', 409)

    # Build item
    item = {
        'pk': 'CI_PROVIDER',
        'sk': provider_id,
        'providerId': provider_id,
        'type': provider_type,
        'name': body.get('name', provider_id),
        'url': body.get('url', ''),
        'user': body.get('user', ''),
        'tokenSecret': body.get('tokenSecret', ''),  # Reference to Secrets Manager
        'createdAt': now,
        'createdBy': actor,
        'updatedAt': now,
        'updatedBy': actor,
    }

    # If token is provided directly, store it (or create secret)
    token = body.get('token')
    if token:
        # Store in Secrets Manager
        token_secret_name = _create_ci_provider_secret(provider_id, {
            'url': item['url'],
            'user': item['user'],
            'token': token,
        })
        item['tokenSecret'] = token_secret_name

    table.put_item(Item=item)

    # Remove token from response
    result = _decimal_to_native(item)
    result.pop('token', None)
    return json_response(201, result)


def _create_ci_provider_secret(provider_id: str, secret_data: Dict) -> str:
    """Create or update secret in Secrets Manager for CI provider."""
    prefix = _get_secrets_prefix().rstrip('/')
    secret_name = f"{prefix}/ci-providers/{provider_id}"

    client = _get_secretsmanager_client()
    secret_string = json.dumps(secret_data)

    try:
        # Try to update existing
        client.put_secret_value(SecretId=secret_name, SecretString=secret_string)
    except client.exceptions.ResourceNotFoundException:
        # Create new
        client.create_secret(
            Name=secret_name,
            SecretString=secret_string,
            Description=f'CI Provider credentials for {provider_id}'
        )

    return secret_name


def update_ci_provider(provider_id: str, body: Dict, actor: str) -> Dict:
    """Update a CI provider."""
    table = _get_table()
    now = _now_iso()

    # Check if exists
    existing = table.get_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id}).get('Item')
    if not existing:
        return error_response('not_found', f'CI Provider {provider_id} not found', 404)

    # Validate type if provided
    provider_type = body.get('type', existing.get('type'))
    if provider_type not in CI_PROVIDER_TYPES:
        return error_response('validation', f'Invalid type. Must be one of: {", ".join(CI_PROVIDER_TYPES)}', 400)

    # Build update
    item = {
        'pk': 'CI_PROVIDER',
        'sk': provider_id,
        'providerId': provider_id,
        'type': provider_type,
        'name': body.get('name', existing.get('name', provider_id)),
        'url': body.get('url', existing.get('url', '')),
        'user': body.get('user', existing.get('user', '')),
        'tokenSecret': body.get('tokenSecret', existing.get('tokenSecret', '')),
        'createdAt': existing.get('createdAt', now),
        'createdBy': existing.get('createdBy', actor),
        'updatedAt': now,
        'updatedBy': actor,
    }

    # If token is provided, update secret
    token = body.get('token')
    if token:
        token_secret_name = _create_ci_provider_secret(provider_id, {
            'url': item['url'],
            'user': item['user'],
            'token': token,
        })
        item['tokenSecret'] = token_secret_name

    table.put_item(Item=item)

    # Remove token from response
    result = _decimal_to_native(item)
    result.pop('token', None)
    return json_response(200, result)


def delete_ci_provider(provider_id: str, actor: str) -> Dict:
    """Delete a CI provider and its secret."""
    table = _get_table()

    # Check if exists
    existing = table.get_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id}).get('Item')
    if not existing:
        return error_response('not_found', f'CI Provider {provider_id} not found', 404)

    # Delete secret if exists
    token_secret = existing.get('tokenSecret')
    if token_secret:
        try:
            client = _get_secretsmanager_client()
            client.delete_secret(SecretId=token_secret, ForceDeleteWithoutRecovery=True)
        except Exception as e:
            print(f"Warning: Failed to delete secret {token_secret}: {e}")

    # Delete from DynamoDB
    table.delete_item(Key={'pk': 'CI_PROVIDER', 'sk': provider_id})
    return json_response(200, {'deleted': provider_id, 'deletedBy': actor})


def test_ci_provider(provider_id: str) -> Dict:
    """Test connection to a CI provider."""
    provider = get_ci_provider_with_credentials(provider_id)
    if not provider:
        return error_response('not_found', f'CI Provider {provider_id} not found', 404)

    provider_type = provider.get('type')
    url = provider.get('url', '').rstrip('/')
    user = provider.get('user', '')
    token = provider.get('token', '')

    if not url:
        return error_response('validation', 'Provider URL is not configured', 400)
    if not token:
        return error_response('validation', 'Provider token is not configured', 400)

    import requests

    try:
        if provider_type == 'jenkins':
            # Test Jenkins API
            if not user:
                return error_response('validation', 'Jenkins user is not configured', 400)
            response = requests.get(
                f"{url}/api/json",
                auth=(user, token),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return json_response(200, {
                'success': True,
                'provider': provider_id,
                'type': provider_type,
                'message': f"Connected to Jenkins: {data.get('description', 'OK')}",
                'version': data.get('version'),
            })

        elif provider_type == 'argocd':
            # Test ArgoCD API
            response = requests.get(
                f"{url}/api/v1/applications",
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
                verify=True
            )
            response.raise_for_status()
            data = response.json()
            app_count = len(data.get('items', []))
            return json_response(200, {
                'success': True,
                'provider': provider_id,
                'type': provider_type,
                'message': f"Connected to ArgoCD: {app_count} applications found",
            })

        else:
            return json_response(200, {
                'success': True,
                'provider': provider_id,
                'type': provider_type,
                'message': f"Provider type '{provider_type}' connection test not implemented",
            })

    except requests.exceptions.HTTPError as e:
        return json_response(200, {
            'success': False,
            'provider': provider_id,
            'type': provider_type,
            'error': f"HTTP {e.response.status_code}: {e.response.reason}",
        })
    except requests.exceptions.ConnectionError as e:
        return json_response(200, {
            'success': False,
            'provider': provider_id,
            'type': provider_type,
            'error': f"Connection failed: {str(e)}",
        })
    except Exception as e:
        return json_response(200, {
            'success': False,
            'provider': provider_id,
            'type': provider_type,
            'error': str(e),
        })


def test_ci_provider_credentials(body: Dict) -> Dict:
    """
    Test connection to a CI provider using credentials from request body.
    This allows testing before saving the provider.
    """
    provider_type = body.get('type')
    url = (body.get('url') or '').rstrip('/')
    user = body.get('user', '')
    token = body.get('token', '')

    if not provider_type:
        return error_response('validation', 'Provider type is required', 400)
    if not url:
        return error_response('validation', 'Provider URL is required', 400)
    if not token:
        return error_response('validation', 'Provider token is required', 400)

    import requests

    try:
        if provider_type == 'jenkins':
            # Test Jenkins API
            if not user:
                return error_response('validation', 'Jenkins user is required', 400)
            response = requests.get(
                f"{url}/api/json",
                auth=(user, token),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return json_response(200, {
                'success': True,
                'type': provider_type,
                'message': f"Connected to Jenkins: {data.get('description', 'OK')}",
                'version': data.get('version'),
            })

        elif provider_type == 'argocd':
            # Test ArgoCD API
            response = requests.get(
                f"{url}/api/v1/applications",
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
                verify=True
            )
            response.raise_for_status()
            data = response.json()
            app_count = len(data.get('items', []))
            return json_response(200, {
                'success': True,
                'type': provider_type,
                'message': f"Connected to ArgoCD: {app_count} applications found",
            })

        else:
            return json_response(200, {
                'success': True,
                'type': provider_type,
                'message': f"Provider type '{provider_type}' connection test not implemented",
            })

    except requests.exceptions.HTTPError as e:
        return json_response(200, {
            'success': False,
            'type': provider_type,
            'error': f"HTTP {e.response.status_code}: {e.response.reason}",
        })
    except requests.exceptions.ConnectionError as e:
        return json_response(200, {
            'success': False,
            'type': provider_type,
            'error': f"Connection failed: {str(e)}",
        })
    except Exception as e:
        return json_response(200, {
            'success': False,
            'type': provider_type,
            'error': str(e),
        })


# =============================================================================
# Export/Import/Validation
# =============================================================================

def export_config() -> Dict:
    """Export all config as JSON."""
    table = _get_table()

    # Scan all items (config table is small)
    response = table.scan()
    items = response.get('Items', [])

    # Organize by type
    export_data = {
        'version': '2.0',
        'exportedAt': _now_iso(),
        'settings': None,
        'projects': [],
        'environments': [],
        'clusters': [],
        'awsAccounts': [],
    }

    for item in items:
        item = _decimal_to_native(item)
        pk = item.get('pk')
        sk = item.get('sk')

        if pk == 'GLOBAL' and sk == 'settings':
            export_data['settings'] = item
        elif pk == 'PROJECT':
            export_data['projects'].append(item)
        elif pk == 'ENV':
            export_data['environments'].append(item)
        elif pk == 'GLOBAL' and sk.startswith('cluster:'):
            export_data['clusters'].append(item)
        elif pk == 'GLOBAL' and sk.startswith('aws-account:'):
            export_data['awsAccounts'].append(item)

    return json_response(200, export_data)


def import_config(body: Dict, actor: str) -> Dict:
    """Import config from JSON (merge or replace)."""
    table = _get_table()
    now = _now_iso()
    mode = body.get('mode', 'merge')  # 'merge' or 'replace'

    if mode == 'replace':
        # Delete all existing items first
        response = table.scan()
        for item in response.get('Items', []):
            table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    imported = {'settings': 0, 'projects': 0, 'environments': 0, 'clusters': 0, 'awsAccounts': 0}

    # Import settings
    if body.get('settings'):
        settings = body['settings']
        settings['pk'] = 'GLOBAL'
        settings['sk'] = 'settings'
        settings['updatedAt'] = now
        settings['updatedBy'] = actor
        table.put_item(Item=settings)
        imported['settings'] = 1

    # Import projects
    for project in body.get('projects', []):
        project['pk'] = 'PROJECT'
        project['sk'] = project['projectId']
        project['updatedAt'] = now
        project['updatedBy'] = actor
        table.put_item(Item=project)
        imported['projects'] += 1

    # Import environments
    for env in body.get('environments', []):
        env['pk'] = 'ENV'
        env['sk'] = f"{env['projectId']}#{env['envId']}"
        env['updatedAt'] = now
        env['updatedBy'] = actor
        table.put_item(Item=env)
        imported['environments'] += 1

    # Import clusters
    for cluster in body.get('clusters', []):
        cluster['pk'] = 'GLOBAL'
        cluster['sk'] = f"cluster:{cluster['clusterId']}"
        cluster['updatedAt'] = now
        cluster['updatedBy'] = actor
        table.put_item(Item=cluster)
        imported['clusters'] += 1

    # Import AWS accounts
    for account in body.get('awsAccounts', []):
        account['pk'] = 'GLOBAL'
        account['sk'] = f"aws-account:{account['accountId']}"
        account['updatedAt'] = now
        account['updatedBy'] = actor
        table.put_item(Item=account)
        imported['awsAccounts'] += 1

    return json_response(200, {'imported': imported, 'mode': mode})


def validate_config(body: Dict) -> Dict:
    """Validate config without saving."""
    errors = []
    warnings = []

    # Validate projects have required fields
    for i, project in enumerate(body.get('projects', [])):
        if not project.get('projectId'):
            errors.append(f'projects[{i}]: missing projectId')

    # Validate environments
    project_ids = {p['projectId'] for p in body.get('projects', []) if p.get('projectId')}
    for i, env in enumerate(body.get('environments', [])):
        if not env.get('projectId'):
            errors.append(f'environments[{i}]: missing projectId')
        elif env['projectId'] not in project_ids:
            warnings.append(f"environments[{i}]: projectId '{env['projectId']}' not in projects list")
        if not env.get('envId'):
            errors.append(f'environments[{i}]: missing envId')

    # Validate clusters
    for i, cluster in enumerate(body.get('clusters', [])):
        if not cluster.get('clusterId'):
            errors.append(f'clusters[{i}]: missing clusterId')

    # Validate AWS accounts
    for i, account in enumerate(body.get('awsAccounts', [])):
        if not account.get('accountId'):
            errors.append(f'awsAccounts[{i}]: missing accountId')

    valid = len(errors) == 0
    return json_response(200 if valid else 400, {
        'valid': valid,
        'errors': errors,
        'warnings': warnings,
    })


def migrate_from_json(body: Dict, actor: str) -> Dict:
    """
    Migrate from infra.config.json format to Config Registry format.

    Expected body contains the old infra.config.json content.
    """
    table = _get_table()
    now = _now_iso()
    migrated = {'settings': 0, 'projects': 0, 'environments': 0, 'clusters': 0, 'awsAccounts': 0}

    # Migrate features, comparison, opsIntegration -> settings
    settings = {
        'pk': 'GLOBAL',
        'sk': 'settings',
        'features': body.get('features', {}),
        'comparison': body.get('comparison', {}),
        'opsIntegration': body.get('opsIntegration', {}),
        'updatedAt': now,
        'updatedBy': actor,
        'version': 1,
    }
    table.put_item(Item=settings)
    migrated['settings'] = 1

    # Migrate crossAccountRoles -> AWS accounts
    for account_id, role_config in body.get('crossAccountRoles', {}).items():
        if account_id.startswith('_'):
            continue
        account = {
            'pk': 'GLOBAL',
            'sk': f'aws-account:{account_id}',
            'accountId': account_id,
            'displayName': role_config.get('displayName', account_id),
            'readRoleArn': role_config.get('readRoleArn', ''),
            'actionRoleArn': role_config.get('actionRoleArn', ''),
            'defaultRegion': role_config.get('region', 'eu-central-1'),
            'updatedAt': now,
            'updatedBy': actor,
        }
        table.put_item(Item=account)
        migrated['awsAccounts'] += 1

    # Migrate eks.clusters -> clusters
    for cluster_id, cluster_config in body.get('eks', {}).get('clusters', {}).items():
        cluster = {
            'pk': 'GLOBAL',
            'sk': f'cluster:{cluster_id}',
            'clusterId': cluster_id,
            'name': cluster_config.get('name', cluster_id),
            'displayName': cluster_config.get('displayName', cluster_id),
            'region': cluster_config.get('region', 'eu-central-1'),
            'accountId': cluster_config.get('accountId', ''),
            'version': cluster_config.get('version', ''),
            'updatedAt': now,
            'updatedBy': actor,
        }
        table.put_item(Item=cluster)
        migrated['clusters'] += 1

    # Migrate projects and environments
    for project_id, project_config in body.get('projects', {}).items():
        if not isinstance(project_config, dict):
            continue

        # Create project
        project = {
            'pk': 'PROJECT',
            'sk': project_id,
            'projectId': project_id,
            'displayName': project_config.get('displayName', project_id),
            'description': project_config.get('description', ''),
            'status': 'active',
            'idpGroupMapping': project_config.get('idpGroupMapping', {}),
            'features': project_config.get('features', {}),
            'pipelines': project_config.get('pipelines', {}),
            'topology': project_config.get('topology', {}),
            'serviceNaming': project_config.get('serviceNaming', {}),
            'updatedAt': now,
            'updatedBy': actor,
            'version': 1,
        }
        table.put_item(Item=project)
        migrated['projects'] += 1

        # Migrate environments
        for env_id, env_config in project_config.get('environments', {}).items():
            if not isinstance(env_config, dict):
                continue

            # Handle infrastructure nested or flat format (legacy migration)
            infra = env_config.get('infrastructure', {})
            discovery_tags = infra.get('discoveryTags', env_config.get('discoveryTags', {}))
            domain_config = infra.get('domainConfig', env_config.get('domainConfig'))

            env = {
                'pk': 'ENV',
                'sk': f'{project_id}#{env_id}',
                'projectId': project_id,
                'envId': env_id,
                'displayName': env_config.get('displayName', env_id),
                'accountId': env_config.get('accountId', ''),
                'region': env_config.get('region', 'eu-central-1'),
                'clusterName': env_config.get('clusterName', ''),
                'namespace': env_config.get('namespace', ''),
                'services': env_config.get('services', []),
                'readRoleArn': env_config.get('readRoleArn'),
                'actionRoleArn': env_config.get('actionRoleArn'),
                'status': env_config.get('status', 'active'),
                'enabled': env_config.get('enabled', True),
                'checkers': env_config.get('checkers', {}),
                'infrastructure': {
                    'defaultTags': discovery_tags,
                    'domainConfig': domain_config,
                    'resources': {},
                },
                'updatedAt': now,
                'updatedBy': actor,
                'version': 1,
            }
            table.put_item(Item=env)
            migrated['environments'] += 1

    return json_response(200, {'migrated': migrated})


# =============================================================================
# Resolution (for terraform-aws-ops)
# =============================================================================

def resolve_config(project_id: str, env_id: str) -> Dict:
    """
    Resolve full config for a project/environment.

    Returns all information needed by terraform-aws-ops Step Functions:
    - Project info
    - Environment config
    - AWS account cross-account role
    - Cluster details
    - Checkers config
    """
    table = _get_table()

    # Get environment
    env_sk = f'{project_id}#{env_id}'
    env_response = table.get_item(Key={'pk': 'ENV', 'sk': env_sk})
    env_item = env_response.get('Item')
    if not env_item:
        return error_response('not_found', f'Environment {env_id} not found in project {project_id}', 404)

    env_item = _decimal_to_native(env_item)

    # Get project
    project_response = table.get_item(Key={'pk': 'PROJECT', 'sk': project_id})
    project_item = _decimal_to_native(project_response.get('Item', {}))

    # Get AWS account (for cross-account role)
    account_id = env_item.get('accountId')
    account_item = {}
    if account_id:
        account_response = table.get_item(Key={'pk': 'GLOBAL', 'sk': f'aws-account:{account_id}'})
        account_item = _decimal_to_native(account_response.get('Item', {}))

    # Get cluster - support flat format (clusterName) or legacy (kubernetes.clusterName)
    cluster_name = env_item.get('clusterName') or env_item.get('kubernetes', {}).get('clusterName', '')
    namespace = env_item.get('namespace') or env_item.get('kubernetes', {}).get('namespace', '')
    cluster_id = env_item.get('kubernetes', {}).get('clusterId', '')
    cluster_item = {}
    if cluster_id:
        cluster_response = table.get_item(Key={'pk': 'GLOBAL', 'sk': f'cluster:{cluster_id}'})
        cluster_item = _decimal_to_native(cluster_response.get('Item', {}))

    # Build resolved config
    resolved = {
        'project': project_id,
        'env': env_id,
        'displayName': env_item.get('displayName', env_id),
        'accountId': account_id,
        'region': env_item.get('region', 'eu-central-1'),
        'clusterName': cluster_name or cluster_item.get('name', ''),
        'namespace': namespace,
        'services': env_item.get('services', []),
        'crossAccountRoleArn': env_item.get('readRoleArn') or account_item.get('readRoleArn', ''),
        'actionRoleArn': env_item.get('actionRoleArn') or account_item.get('actionRoleArn', ''),
        'checkers': env_item.get('checkers', {}),
        'infrastructure': env_item.get('infrastructure', {}),
        'status': env_item.get('status', 'active'),
        'enabled': env_item.get('enabled', True),
        # Additional context
        'projectDisplayName': project_item.get('displayName', project_id),
        'clusterVersion': cluster_item.get('version', ''),
    }

    return json_response(200, resolved)


# =============================================================================
# Secrets Management (for CI/CD provider tokens)
# =============================================================================

def _get_secrets_prefix() -> str:
    """Get the secrets prefix from settings."""
    table = _get_table()
    response = table.get_item(Key={'pk': 'GLOBAL', 'sk': 'settings'})
    item = response.get('Item', {})
    return item.get('secretsPrefix', '/dashborion')


def _build_secret_name(secret_type: str, project: Optional[str] = None) -> str:
    """
    Build secret name from prefix, project (optional), and type.

    Patterns:
    - Global secret: {prefix}/{type}  (e.g., /dashborion/jenkins-token)
    - Project secret: {prefix}/{project}/{type}  (e.g., /dashborion/rubix/argocd-token)
    """
    prefix = _get_secrets_prefix().rstrip('/')
    if project:
        return f"{prefix}/{project}/{secret_type}"
    return f"{prefix}/{secret_type}"


def _get_secretsmanager_client():
    """Get Secrets Manager client."""
    return boto3.client('secretsmanager')


def create_or_update_secret(secret_type: str, body: Dict, actor: str) -> Dict:
    """
    Create or update a secret in AWS Secrets Manager.

    Body:
    - value: The secret value (required)
    - url: Optional URL for the provider (e.g., Jenkins URL)
    - user: Optional username for the provider (e.g., Jenkins user)
    - project: Optional project scope (creates project-specific secret)
    - description: Optional description

    Secret types:
    - jenkins-token: Jenkins API token
    - argocd-token: ArgoCD API token
    - github-token: GitHub personal access token
    - bitbucket-token: Bitbucket app password
    """
    if not secret_type:
        return error_response('validation', 'secret_type is required', 400)

    value = body.get('value')
    if not value:
        return error_response('validation', 'value is required', 400)

    project = body.get('project')
    description = body.get('description', f'Dashborion {secret_type} token')

    # Build secret data including optional url and user
    secret_data = {'token': value}
    if body.get('url'):
        secret_data['url'] = body['url']
    if body.get('user'):
        secret_data['user'] = body['user']

    secret_name = _build_secret_name(secret_type, project)
    client = _get_secretsmanager_client()

    try:
        # Try to create the secret
        response = client.create_secret(
            Name=secret_name,
            Description=description,
            SecretString=json.dumps(secret_data),
            Tags=[
                {'Key': 'ManagedBy', 'Value': 'dashborion'},
                {'Key': 'SecretType', 'Value': secret_type},
                {'Key': 'CreatedBy', 'Value': actor},
            ]
        )
        return json_response(201, {
            'secretName': secret_name,
            'secretArn': response['ARN'],
            'created': True,
            'message': f'Secret {secret_name} created successfully'
        })
    except client.exceptions.ResourceExistsException:
        # Secret exists, update it
        response = client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(secret_data)
        )
        # Update description if provided
        if description:
            client.update_secret(
                SecretId=secret_name,
                Description=description
            )
        return json_response(200, {
            'secretName': secret_name,
            'secretArn': response['ARN'],
            'created': False,
            'message': f'Secret {secret_name} updated successfully'
        })
    except Exception as e:
        return error_response('secrets_error', f'Failed to manage secret: {str(e)}', 500)


def delete_secret(secret_type: str, body: Dict, actor: str) -> Dict:
    """Delete a secret from AWS Secrets Manager."""
    if not secret_type:
        return error_response('validation', 'secret_type is required', 400)

    project = body.get('project')
    secret_name = _build_secret_name(secret_type, project)
    client = _get_secretsmanager_client()

    try:
        # Schedule deletion (recoverable for 7 days)
        client.delete_secret(
            SecretId=secret_name,
            RecoveryWindowInDays=7
        )
        return json_response(200, {
            'secretName': secret_name,
            'deleted': True,
            'message': f'Secret {secret_name} scheduled for deletion (recoverable for 7 days)'
        })
    except client.exceptions.ResourceNotFoundException:
        return error_response('not_found', f'Secret {secret_name} not found', 404)
    except Exception as e:
        return error_response('secrets_error', f'Failed to delete secret: {str(e)}', 500)


def get_secret_info(secret_type: str, body: Dict) -> Dict:
    """
    Get secret metadata (not the value) from AWS Secrets Manager.

    Returns info about whether the secret exists and when it was last modified.
    """
    if not secret_type:
        return error_response('validation', 'secret_type is required', 400)

    project = body.get('project') if body else None
    secret_name = _build_secret_name(secret_type, project)
    client = _get_secretsmanager_client()

    try:
        response = client.describe_secret(SecretId=secret_name)
        return json_response(200, {
            'secretName': secret_name,
            'secretArn': response.get('ARN'),
            'exists': True,
            'lastModified': response.get('LastChangedDate').isoformat() if response.get('LastChangedDate') else None,
            'createdDate': response.get('CreatedDate').isoformat() if response.get('CreatedDate') else None,
            'description': response.get('Description'),
        })
    except client.exceptions.ResourceNotFoundException:
        return json_response(200, {
            'secretName': secret_name,
            'exists': False,
        })
    except Exception as e:
        return error_response('secrets_error', f'Failed to get secret info: {str(e)}', 500)


def test_provider_connection(body: Dict) -> Dict:
    """
    Test connection to a CI/CD provider.

    Body:
    - provider: jenkins, argocd, github, bitbucket
    - project: Optional project scope
    - url: Provider URL (for jenkins, argocd)
    - user: Username (for jenkins)
    - token: Optional token to test (if not provided, retrieves from Secrets Manager)
    """
    import requests

    provider = body.get('provider')
    if not provider:
        return error_response('validation', 'provider is required', 400)

    # Check if token is provided directly (for testing before save)
    token = body.get('token')

    if not token:
        # Retrieve from Secrets Manager
        project = body.get('project')
        secret_type = f'{provider}-token'
        secret_name = _build_secret_name(secret_type, project)

        client = _get_secretsmanager_client()
        try:
            response = client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response['SecretString'])
            token = secret_data.get('token', '')
        except client.exceptions.ResourceNotFoundException:
            return error_response('not_found', f'Secret {secret_name} not found. Please save credentials first or provide token in request.', 404)
        except Exception as e:
            return error_response('secrets_error', f'Failed to retrieve secret: {str(e)}', 500)

    # Test connection based on provider
    try:
        if provider == 'jenkins':
            url = body.get('url', '').rstrip('/')
            user = body.get('user', '')
            if not url:
                return error_response('validation', 'url is required for Jenkins', 400)
            if not user:
                return error_response('validation', 'user is required for Jenkins', 400)

            # Test Jenkins API
            test_url = f'{url}/api/json'
            resp = requests.get(test_url, auth=(user, token), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return json_response(200, {
                    'success': True,
                    'provider': 'jenkins',
                    'message': 'Connection successful',
                    'details': {
                        'mode': data.get('mode', 'unknown'),
                        'numExecutors': data.get('numExecutors', 0),
                    }
                })
            else:
                return json_response(200, {
                    'success': False,
                    'provider': 'jenkins',
                    'message': f'Connection failed: HTTP {resp.status_code}',
                })

        elif provider == 'argocd':
            url = body.get('url', '').rstrip('/')
            if not url:
                return error_response('validation', 'url is required for ArgoCD', 400)

            # Test ArgoCD API
            test_url = f'{url}/api/v1/session/userinfo'
            headers = {'Authorization': f'Bearer {token}'}
            resp = requests.get(test_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return json_response(200, {
                    'success': True,
                    'provider': 'argocd',
                    'message': 'Connection successful',
                    'details': {
                        'username': data.get('username', 'unknown'),
                        'iss': data.get('iss', 'argocd'),
                    }
                })
            else:
                return json_response(200, {
                    'success': False,
                    'provider': 'argocd',
                    'message': f'Connection failed: HTTP {resp.status_code}',
                })

        elif provider == 'github':
            # Test GitHub API
            headers = {'Authorization': f'token {token}'}
            resp = requests.get('https://api.github.com/user', headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return json_response(200, {
                    'success': True,
                    'provider': 'github',
                    'message': 'Connection successful',
                    'details': {
                        'login': data.get('login', 'unknown'),
                        'name': data.get('name', ''),
                    }
                })
            else:
                return json_response(200, {
                    'success': False,
                    'provider': 'github',
                    'message': f'Connection failed: HTTP {resp.status_code}',
                })

        else:
            return error_response('validation', f'Unsupported provider: {provider}', 400)

    except requests.exceptions.Timeout:
        return json_response(200, {
            'success': False,
            'provider': provider,
            'message': 'Connection timed out',
        })
    except requests.exceptions.ConnectionError as e:
        return json_response(200, {
            'success': False,
            'provider': provider,
            'message': f'Connection error: {str(e)}',
        })
    except Exception as e:
        return error_response('test_error', f'Test failed: {str(e)}', 500)


def discover_pipelines(body: Dict) -> Dict:
    """
    Discover available pipelines from CI/CD providers.

    Body:
    - provider: jenkins, argocd
    - url: Provider URL
    - user: Username (for jenkins)
    - token: API token (optional, will use stored if not provided)
    - path: Optional path to list jobs from (for jenkins folders)
    - project: Optional project scope for stored token
    """
    import requests

    provider = body.get('provider')
    if not provider:
        return error_response('validation', 'provider is required', 400)

    # Get token and credentials from body or Secrets Manager
    token = body.get('token')
    secret_data = {}

    if not token:
        project = body.get('project')
        secret_type = f'{provider}-token'
        secret_name = _build_secret_name(secret_type, project)

        client = _get_secretsmanager_client()
        try:
            response = client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response['SecretString'])
            token = secret_data.get('token', '')
        except client.exceptions.ResourceNotFoundException:
            return error_response('not_found', f'No token configured for {provider}. Please configure it first or provide token in request.', 404)
        except Exception as e:
            return error_response('secrets_error', f'Failed to retrieve token: {str(e)}', 500)

    try:
        if provider == 'jenkins':
            # Get URL and user from request or stored secret
            url = body.get('url') or secret_data.get('url', '')
            url = url.rstrip('/') if url else ''
            user = body.get('user') or secret_data.get('user', '')
            path = body.get('path', '')  # Folder path (e.g., 'RubixDeployment/EKS')

            if not url:
                return error_response('validation', 'url is required for Jenkins. Configure it in Settings first.', 400)
            if not user:
                return error_response('validation', 'user is required for Jenkins. Configure it in Settings first.', 400)

            # Build API URL for listing jobs
            if path:
                # Encode path for Jenkins API (replace / with /job/)
                encoded_path = '/job/'.join(path.split('/'))
                api_url = f'{url}/job/{encoded_path}/api/json?tree=jobs[name,url,_class,jobs[name,url,_class]]'
            else:
                api_url = f'{url}/api/json?tree=jobs[name,url,_class,jobs[name,url,_class]]'

            resp = requests.get(api_url, auth=(user, token), timeout=15)

            if resp.status_code != 200:
                return json_response(200, {
                    'success': False,
                    'provider': 'jenkins',
                    'message': f'Failed to list jobs: HTTP {resp.status_code}',
                    'items': []
                })

            data = resp.json()
            jobs = data.get('jobs', [])

            # Parse jobs into a flat list with folder structure
            items = []
            for job in jobs:
                job_class = job.get('_class', '')
                job_name = job.get('name', '')
                job_url = job.get('url', '')

                # Determine job type
                if 'Folder' in job_class or 'OrganizationFolder' in job_class:
                    job_type = 'folder'
                elif 'WorkflowJob' in job_class or 'FreeStyleProject' in job_class:
                    job_type = 'job'
                else:
                    job_type = 'other'

                full_path = f'{path}/{job_name}' if path else job_name

                items.append({
                    'name': job_name,
                    'path': full_path,
                    'type': job_type,
                    'url': job_url,
                    '_class': job_class
                })

                # If it's a folder with nested jobs, include them
                nested_jobs = job.get('jobs', [])
                for nested in nested_jobs:
                    nested_name = nested.get('name', '')
                    nested_class = nested.get('_class', '')
                    nested_type = 'folder' if 'Folder' in nested_class else 'job'
                    nested_path = f'{full_path}/{nested_name}'

                    items.append({
                        'name': nested_name,
                        'path': nested_path,
                        'type': nested_type,
                        'url': nested.get('url', ''),
                        '_class': nested_class,
                        'parent': full_path
                    })

            return json_response(200, {
                'success': True,
                'provider': 'jenkins',
                'currentPath': path or '/',
                'items': items
            })

        elif provider == 'argocd':
            # Get URL from request or stored secret
            url = body.get('url') or secret_data.get('url', '')
            url = url.rstrip('/') if url else ''
            if not url:
                return error_response('validation', 'url is required for ArgoCD. Configure it in Settings first.', 400)

            # List all applications
            headers = {'Authorization': f'Bearer {token}'}
            resp = requests.get(f'{url}/api/v1/applications', headers=headers, timeout=15)

            if resp.status_code != 200:
                return json_response(200, {
                    'success': False,
                    'provider': 'argocd',
                    'message': f'Failed to list applications: HTTP {resp.status_code}',
                    'items': []
                })

            data = resp.json()
            apps = data.get('items', [])

            items = []
            for app in apps:
                metadata = app.get('metadata', {})
                spec = app.get('spec', {})
                status = app.get('status', {})

                app_name = metadata.get('name', '')
                namespace = metadata.get('namespace', 'argocd')
                project = spec.get('project', 'default')

                # Get sync and health status
                sync_status = status.get('sync', {}).get('status', 'Unknown')
                health_status = status.get('health', {}).get('status', 'Unknown')

                # Get destination info
                destination = spec.get('destination', {})
                dest_server = destination.get('server', '')
                dest_namespace = destination.get('namespace', '')

                items.append({
                    'name': app_name,
                    'path': f'{project}/{app_name}',
                    'type': 'application',
                    'project': project,
                    'namespace': namespace,
                    'destination': {
                        'server': dest_server,
                        'namespace': dest_namespace
                    },
                    'status': {
                        'sync': sync_status,
                        'health': health_status
                    },
                    'url': f'{url}/applications/{app_name}'
                })

            return json_response(200, {
                'success': True,
                'provider': 'argocd',
                'items': items
            })

        else:
            return error_response('validation', f'Discovery not supported for provider: {provider}', 400)

    except requests.exceptions.Timeout:
        return json_response(200, {
            'success': False,
            'provider': provider,
            'message': 'Request timed out',
            'items': []
        })
    except requests.exceptions.ConnectionError as e:
        return json_response(200, {
            'success': False,
            'provider': provider,
            'message': f'Connection error: {str(e)}',
            'items': []
        })
    except Exception as e:
        return error_response('discover_error', f'Discovery failed: {str(e)}', 500)


# =============================================================================
# Frontend Config (for React app)
# =============================================================================

def get_frontend_config() -> Dict:
    """
    Build frontend-compatible config from DynamoDB.

    Returns config in the format expected by ConfigContext.jsx:
    - global: branding, SSO portal URL, default region
    - api: API configuration
    - auth: auth configuration
    - features: feature flags
    - projects: map of projectId -> project config with environments
    - defaultProject: first project ID
    """
    table = _get_table()

    # Get settings
    settings_response = table.get_item(Key={'pk': 'GLOBAL', 'sk': 'settings'})
    settings = _decimal_to_native(settings_response.get('Item', {}))

    # Get all projects
    projects_response = table.query(
        KeyConditionExpression=Key('pk').eq('PROJECT')
    )
    project_items = [_decimal_to_native(item) for item in projects_response.get('Items', [])]

    # Get all environments
    env_response = table.query(
        KeyConditionExpression=Key('pk').eq('ENV')
    )
    env_items = [_decimal_to_native(item) for item in env_response.get('Items', [])]

    # Get all AWS accounts (for accounts map)
    accounts_response = table.query(
        KeyConditionExpression=Key('pk').eq('GLOBAL') & Key('sk').begins_with('aws-account:')
    )
    account_items = [_decimal_to_native(item) for item in accounts_response.get('Items', [])]

    # Build accounts map
    aws_accounts = {}
    for account in account_items:
        account_id = account.get('accountId')
        if account_id:
            aws_accounts[account_id] = {
                'displayName': account.get('displayName', account_id),
                'readRoleArn': account.get('readRoleArn', ''),
                'actionRoleArn': account.get('actionRoleArn', ''),
                'defaultRegion': account.get('defaultRegion', 'eu-central-1'),
            }

    # Group environments by projectId
    envs_by_project: Dict[str, List[Dict]] = {}
    for env in env_items:
        project_id = env.get('projectId')
        if project_id:
            if project_id not in envs_by_project:
                envs_by_project[project_id] = []
            envs_by_project[project_id].append(env)

    # Build projects map
    projects = {}
    default_project = None

    for project in project_items:
        project_id = project.get('projectId')
        if not project_id:
            continue

        if default_project is None:
            default_project = project_id

        # Get environments for this project
        project_envs = envs_by_project.get(project_id, [])

        # Build environments as object (envId -> env config) for frontend
        environments_map = {}
        environment_names = []
        all_services = set()

        for env in project_envs:
            env_id = env.get('envId')
            if not env_id:
                continue

            environment_names.append(env_id)

            # Collect services from environment
            env_services = env.get('services', [])
            all_services.update(env_services)

            # Build env config for frontend
            environments_map[env_id] = {
                'displayName': env.get('displayName', env_id),
                'accountId': env.get('accountId', ''),
                'region': env.get('region', 'eu-central-1'),
                'clusterName': env.get('clusterName', ''),
                'namespace': env.get('namespace', ''),
                'services': env_services,
                'status': env.get('status', 'active'),
                'enabled': env.get('enabled', True),
                'infrastructure': env.get('infrastructure', {}),
                'topology': env.get('topology', {}),
                'checkers': env.get('checkers', {}),
            }

        # Build project config for frontend
        projects[project_id] = {
            'name': project.get('displayName', project_id),
            'description': project.get('description', ''),
            'status': project.get('status', 'active'),
            'orchestratorType': project.get('orchestratorType') or None,
            'environments': environment_names,
            'environmentsConfig': environments_map,
            'services': list(all_services) or project.get('services', []),
            'serviceNaming': project.get('serviceNaming', {}),
            'envColors': project.get('envColors', {}),
            'features': project.get('features', {}),
            'pipelines': project.get('pipelines', {}),
            'topology': project.get('topology', {}),
            'idpGroupMapping': project.get('idpGroupMapping', {}),
            'aws': {
                'accounts': aws_accounts,
            },
        }

    # Build final config
    frontend_config = {
        'global': {
            'logo': settings.get('branding', {}).get('logo', '/logo.svg'),
            'logoAlt': settings.get('branding', {}).get('logoAlt', 'Dashboard'),
            'ssoPortalUrl': settings.get('aws', {}).get('ssoPortalUrl', ''),
            'defaultRegion': settings.get('aws', {}).get('defaultRegion', 'eu-central-1'),
        },
        'api': settings.get('api', {}),
        'auth': settings.get('auth', {}),
        'features': settings.get('features', {}),
        'projects': projects,
        'defaultProject': default_project,
    }

    return json_response(200, frontend_config)
