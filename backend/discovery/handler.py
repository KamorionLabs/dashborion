"""
Discovery Lambda Handler.

Handles AWS resource discovery endpoints for the Admin UI.
Discovers resources in target AWS accounts using cross-account role assumption.

Endpoints:
- GET /api/config/discovery/{accountId}/{resourceType}
- GET /api/config/discovery/{accountId}/{resourceType}?vpc=vpc-xxx
- GET /api/config/discovery/{accountId}/{resourceType}?tags=key:value

Resource types: vpc, route53, eks, ecs, rds, documentdb, elasticache, efs, alb, sg, s3
"""

import json
import os
import re
from typing import Dict, Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from shared.rbac import get_auth_context, is_global_admin
from shared.response import (
    json_response,
    error_response,
    get_method,
    get_path,
)

from .providers import (
    DISCOVERY_FUNCTIONS,
    discover_vpcs,
    discover_route53_zones,
    discover_eks_clusters,
    discover_eks_namespaces,
    discover_eks_workloads,
    discover_ecs_clusters,
    discover_ecs_services,
    discover_rds_clusters,
    discover_documentdb_clusters,
    discover_elasticache_clusters,
    discover_efs_filesystems,
    discover_albs,
    discover_security_groups,
    discover_s3_buckets,
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


def get_aws_account(account_id: str) -> Optional[Dict[str, Any]]:
    """
    Get AWS account configuration from Config Registry.

    Args:
        account_id: AWS account ID (12-digit string)

    Returns:
        Account configuration dict or None if not found
    """
    table = _get_table()
    response = table.get_item(
        Key={
            'pk': 'GLOBAL',
            'sk': f'aws-account:{account_id}'
        }
    )
    return response.get('Item')


def test_connection(role_arn: str, region: str) -> Dict[str, Any]:
    """
    Test cross-account role assumption.

    Returns:
        Dict with success status and account info or error
    """
    try:
        sts = boto3.client('sts')
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='dashborion-test-connection'
        )

        # Get caller identity in target account
        target_sts = boto3.client(
            'sts',
            aws_access_key_id=assumed['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed['Credentials']['SecretAccessKey'],
            aws_session_token=assumed['Credentials']['SessionToken']
        )
        identity = target_sts.get_caller_identity()

        return {
            'success': True,
            'account': identity['Account'],
            'arn': identity['Arn'],
            'userId': identity['UserId'],
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


def parse_tags_param(tags_param: str) -> Dict[str, str]:
    """
    Parse tags query parameter.

    Format: "key1:value1,key2:value2"

    Returns:
        Dict of tag key-value pairs
    """
    if not tags_param:
        return {}

    tags = {}
    for pair in tags_param.split(','):
        if ':' in pair:
            key, value = pair.split(':', 1)
            tags[key.strip()] = value.strip()
    return tags


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for discovery endpoints."""
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # All discovery endpoints require global admin
    if not is_global_admin(auth):
        return error_response('forbidden', 'Global admin access required', 403)

    # Parse path parameters
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}

    try:
        return route_request(path, method, path_params, query_params)
    except Exception as e:
        print(f"Error in discovery handler: {e}")
        import traceback
        traceback.print_exc()
        return error_response('internal_error', str(e), 500)


def route_request(path: str, method: str, path_params: Dict, query_params: Dict) -> Dict:
    """Route request to appropriate handler."""

    # Direct role test - test any roleArn without saving
    # GET /api/config/discovery/test-role?roleArn=arn:aws:iam::...
    if path == '/api/config/discovery/test-role':
        role_arn = query_params.get('roleArn')
        if not role_arn:
            return error_response('bad_request', 'roleArn query parameter is required', 400)
        return handle_test_role(role_arn)

    # Legacy test connection endpoint (uses roleArn from DB)
    # GET /api/config/discovery/{accountId}/test
    if re.match(r'^/api/config/discovery/[^/]+/test$', path):
        account_id = path_params.get('accountId')
        if method == 'GET':
            return handle_test_connection(account_id)

    # Resource discovery endpoint
    # GET /api/config/discovery/{accountId}/{resourceType}
    if re.match(r'^/api/config/discovery/[^/]+/[^/]+$', path):
        account_id = path_params.get('accountId')
        resource_type = path_params.get('resourceType')
        if method == 'GET':
            return handle_discover(account_id, resource_type, query_params)

    return error_response('not_found', f'Unknown path: {path}', 404)


def handle_test_role(role_arn: str) -> Dict:
    """
    Handle direct role test request (uses roleArn from query, not from DB).

    GET /api/config/discovery/test-role?roleArn=arn:aws:iam::123456789012:role/my-role
    """
    result = test_connection(role_arn, 'eu-central-1')  # Region doesn't matter for STS
    return json_response(200, {
        'roleArn': role_arn,
        **result,
    })


def handle_test_connection(account_id: str) -> Dict:
    """
    Handle test connection request (legacy - uses roleArn from DB).

    GET /api/config/discovery/{accountId}/test
    """
    # Get account config
    account = get_aws_account(account_id)
    if not account:
        return error_response('not_found', f'AWS account {account_id} not found in config', 404)

    role_arn = account.get('readRoleArn')
    if not role_arn:
        return error_response('bad_request', f'AWS account {account_id} has no readRoleArn configured', 400)

    result = test_connection(role_arn, 'eu-central-1')
    return json_response(200, {
        'accountId': account_id,
        'roleArn': role_arn,
        **result,
    })


def handle_discover(account_id: str, resource_type: str, query_params: Dict) -> Dict:
    """
    Handle resource discovery request.

    GET /api/config/discovery/{accountId}/{resourceType}
    """
    # Get account config
    account = get_aws_account(account_id)
    if not account:
        return error_response('not_found', f'AWS account {account_id} not found in config', 404)

    role_arn = account.get('readRoleArn')
    if not role_arn:
        return error_response('bad_request', f'AWS account {account_id} has no readRoleArn configured', 400)

    # Get region from query param or account default
    region = query_params.get('region') or account.get('defaultRegion', 'eu-central-1')

    try:
        # Call the appropriate discovery function
        if resource_type == 'alb':
            # ALB supports tag filtering
            tags = parse_tags_param(query_params.get('tags', ''))
            resources = discover_albs(role_arn, region, tags if tags else None)
        elif resource_type == 'sg':
            # Security groups support VPC filtering
            vpc_id = query_params.get('vpc')
            resources = discover_security_groups(role_arn, region, vpc_id)
        elif resource_type == 'ecs-services':
            # ECS services require cluster name
            cluster = query_params.get('cluster')
            if not cluster:
                return error_response('bad_request', 'cluster query parameter is required for ecs-services', 400)
            resources = discover_ecs_services(role_arn, region, cluster)
        elif resource_type == 'eks-namespaces':
            # EKS namespaces require cluster name
            cluster = query_params.get('cluster')
            if not cluster:
                return error_response('bad_request', 'cluster query parameter is required for eks-namespaces', 400)
            resources = discover_eks_namespaces(role_arn, region, cluster)
        elif resource_type == 'eks-workloads':
            # EKS workloads require cluster and namespace
            cluster = query_params.get('cluster')
            namespace = query_params.get('namespace')
            if not cluster or not namespace:
                return error_response('bad_request', 'cluster and namespace query parameters are required for eks-workloads', 400)
            resources = discover_eks_workloads(role_arn, region, cluster, namespace)
        elif resource_type in DISCOVERY_FUNCTIONS:
            # Standard discovery
            discovery_fn = DISCOVERY_FUNCTIONS[resource_type]
            resources = discovery_fn(role_arn, region)
        else:
            valid_types = list(DISCOVERY_FUNCTIONS.keys()) + ['ecs-services', 'eks-namespaces', 'eks-workloads']
            return error_response(
                'bad_request',
                f'Unknown resource type: {resource_type}. Valid types: {", ".join(valid_types)}',
                400
            )

        return json_response(200, {
            'accountId': account_id,
            'region': region,
            'resourceType': resource_type,
            'count': len(resources),
            'resources': resources,
        })

    except Exception as e:
        print(f"Discovery error for {resource_type} in account {account_id}: {e}")
        import traceback
        traceback.print_exc()
        return error_response(
            'discovery_error',
            f'Failed to discover {resource_type}: {str(e)}',
            500
        )
