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

    # All config endpoints require global admin
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
        })
    return json_response(200, _decimal_to_native(item))


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
        'features': body.get('features', {}),
        'comparison': body.get('comparison', {}),
        'opsIntegration': body.get('opsIntegration', {}),
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
