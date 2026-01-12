"""
Config Registry Commands for Dashborion CLI

Provides commands for managing the Config Registry:
- export: Export config to JSON file
- import: Import config from JSON file
- migrate: Migrate from old infra.config.json format
- validate: Validate config without saving
- show: Show current config (settings, projects, environments, etc.)

Supports two modes:
- API mode (default): Use when Dashborion is deployed
- Direct mode (--direct): Access DynamoDB directly (requires AWS credentials)
"""

import click
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

import requests


# =============================================================================
# DynamoDB Direct Access (for --direct mode)
# =============================================================================

_dynamodb = None


def _get_dynamodb(profile: Optional[str] = None, region: Optional[str] = None):
    """Get DynamoDB resource (lazy init)"""
    global _dynamodb
    if _dynamodb is None:
        import boto3
        session_args = {}
        if profile:
            session_args['profile_name'] = profile
        if region:
            session_args['region_name'] = region
        session = boto3.Session(**session_args)
        _dynamodb = session.resource('dynamodb')
    return _dynamodb


def _get_table(table_name: str, profile: Optional[str] = None, region: Optional[str] = None):
    """Get DynamoDB table"""
    return _get_dynamodb(profile, region).Table(table_name)


def _decimal_to_native(obj):
    """Convert Decimal to int/float for JSON serialization"""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    return obj


def _now_iso() -> str:
    """Get current timestamp in ISO format"""
    return datetime.utcnow().isoformat() + 'Z'


# =============================================================================
# API Mode Functions
# =============================================================================

def _api_request(method: str, path: str, data: dict = None) -> dict:
    """Make authenticated API request"""
    from dashborion.utils.api_client import get_api_client, AuthenticationError

    try:
        client = get_api_client()

        if method == 'GET':
            response = client.get(path)
        elif method == 'POST':
            response = client.post(path, json_data=data)
        elif method == 'PUT':
            response = client.put(path, json_data=data)
        else:
            raise ValueError(f"Unknown method: {method}")

        if response.status_code == 401:
            raise click.ClickException("Unauthorized. Please authenticate first: dashborion auth login")
        if response.status_code == 403:
            raise click.ClickException("Permission denied. Admin privileges required.")

        return response.json()

    except AuthenticationError as e:
        raise click.ClickException(str(e))
    except requests.RequestException as e:
        raise click.ClickException(f"API request failed: {e}")


# =============================================================================
# Direct Mode Functions
# =============================================================================

def _direct_export(table_name: str, profile: Optional[str], region: Optional[str]) -> dict:
    """Export config directly from DynamoDB"""
    from boto3.dynamodb.conditions import Key

    table = _get_table(table_name, profile, region)

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

        # Remove pk/sk from exported data (clean format)
        clean_item = {k: v for k, v in item.items() if k not in ('pk', 'sk')}

        if pk == 'GLOBAL' and sk == 'settings':
            export_data['settings'] = clean_item
        elif pk == 'PROJECT':
            clean_item['projectId'] = sk
            export_data['projects'].append(clean_item)
        elif pk == 'ENV':
            # sk format: projectId#envId
            parts = sk.split('#', 1)
            if len(parts) == 2:
                clean_item['projectId'] = parts[0]
                clean_item['envId'] = parts[1]
            export_data['environments'].append(clean_item)
        elif pk == 'GLOBAL' and sk.startswith('cluster:'):
            clean_item['clusterId'] = sk.replace('cluster:', '')
            export_data['clusters'].append(clean_item)
        elif pk == 'GLOBAL' and sk.startswith('aws-account:'):
            clean_item['accountId'] = sk.replace('aws-account:', '')
            export_data['awsAccounts'].append(clean_item)

    return export_data


def _direct_import(table_name: str, data: dict, profile: Optional[str], region: Optional[str],
                   mode: str, actor: str) -> dict:
    """Import config directly to DynamoDB"""
    table = _get_table(table_name, profile, region)
    now = _now_iso()

    if mode == 'replace':
        # Delete all existing items first
        response = table.scan()
        for item in response.get('Items', []):
            table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    imported = {'settings': 0, 'projects': 0, 'environments': 0, 'clusters': 0, 'awsAccounts': 0}

    # Import settings
    if data.get('settings'):
        settings = data['settings'].copy()
        settings['pk'] = 'GLOBAL'
        settings['sk'] = 'settings'
        settings['updatedAt'] = now
        settings['updatedBy'] = actor
        table.put_item(Item=settings)
        imported['settings'] = 1

    # Import projects
    for project in data.get('projects', []):
        item = project.copy()
        item['pk'] = 'PROJECT'
        item['sk'] = project['projectId']
        item['updatedAt'] = now
        item['updatedBy'] = actor
        table.put_item(Item=item)
        imported['projects'] += 1

    # Import environments
    for env in data.get('environments', []):
        item = env.copy()
        item['pk'] = 'ENV'
        item['sk'] = f"{env['projectId']}#{env['envId']}"
        item['updatedAt'] = now
        item['updatedBy'] = actor
        table.put_item(Item=item)
        imported['environments'] += 1

    # Import clusters
    for cluster in data.get('clusters', []):
        item = cluster.copy()
        item['pk'] = 'GLOBAL'
        item['sk'] = f"cluster:{cluster['clusterId']}"
        item['updatedAt'] = now
        item['updatedBy'] = actor
        table.put_item(Item=item)
        imported['clusters'] += 1

    # Import AWS accounts
    for account in data.get('awsAccounts', []):
        item = account.copy()
        item['pk'] = 'GLOBAL'
        item['sk'] = f"aws-account:{account['accountId']}"
        item['updatedAt'] = now
        item['updatedBy'] = actor
        table.put_item(Item=item)
        imported['awsAccounts'] += 1

    return imported


def _migrate_infra_config(old_config: dict) -> dict:
    """Convert old infra.config.json format to new Config Registry format"""
    new_config = {
        'version': '2.0',
        'exportedAt': _now_iso(),
        'settings': {
            'features': old_config.get('features', {}),
            'comparison': old_config.get('comparison', {}),
            'opsIntegration': old_config.get('opsIntegration', {}),
        },
        'projects': [],
        'environments': [],
        'clusters': [],
        'awsAccounts': [],
    }

    # Migrate crossAccountRoles -> AWS accounts
    for account_id, role_config in old_config.get('crossAccountRoles', {}).items():
        if account_id.startswith('_'):
            continue
        if not isinstance(role_config, dict):
            continue
        new_config['awsAccounts'].append({
            'accountId': account_id,
            'displayName': role_config.get('displayName', account_id),
            'readRoleArn': role_config.get('readRoleArn', ''),
            'actionRoleArn': role_config.get('actionRoleArn', ''),
            'defaultRegion': role_config.get('region', 'eu-central-1'),
        })

    # Migrate eks.clusters -> clusters
    for cluster_id, cluster_config in old_config.get('eks', {}).get('clusters', {}).items():
        if not isinstance(cluster_config, dict):
            continue
        new_config['clusters'].append({
            'clusterId': cluster_id,
            'name': cluster_config.get('name', cluster_id),
            'displayName': cluster_config.get('displayName', cluster_id),
            'region': cluster_config.get('region', 'eu-central-1'),
            'accountId': cluster_config.get('accountId', ''),
            'version': cluster_config.get('version', ''),
        })

    # Migrate projects and environments
    for project_id, project_config in old_config.get('projects', {}).items():
        if not isinstance(project_config, dict):
            continue

        # Create project
        new_config['projects'].append({
            'projectId': project_id,
            'displayName': project_config.get('displayName', project_id),
            'description': project_config.get('description', ''),
            'status': 'active',
            'idpGroupMapping': project_config.get('idpGroupMapping', {}),
            'features': project_config.get('features', {}),
            'pipelines': project_config.get('pipelines', {}),
            'topology': project_config.get('topology', {}),
        })

        # Migrate environments
        for env_id, env_config in project_config.get('environments', {}).items():
            if not isinstance(env_config, dict):
                continue

            new_config['environments'].append({
                'projectId': project_id,
                'envId': env_id,
                'displayName': env_config.get('displayName', env_id),
                'accountId': env_config.get('accountId', ''),
                'region': env_config.get('region', 'eu-central-1'),
                'kubernetes': {
                    'clusterId': env_config.get('clusterId', ''),
                    'clusterName': env_config.get('clusterName', ''),
                    'namespace': env_config.get('namespace', ''),
                },
                'readRoleArn': env_config.get('readRoleArn'),
                'actionRoleArn': env_config.get('actionRoleArn'),
                'status': env_config.get('status', 'active'),
                'enabled': env_config.get('enabled', True),
                'checkers': env_config.get('checkers', {}),
                'discoveryTags': env_config.get('discoveryTags', {}),
                'databases': env_config.get('databases', []),
            })

    return new_config


def _validate_config(data: dict) -> tuple:
    """Validate config data, returns (is_valid, errors, warnings)"""
    errors = []
    warnings = []

    # Validate projects have required fields
    for i, project in enumerate(data.get('projects', [])):
        if not project.get('projectId'):
            errors.append(f"projects[{i}]: missing projectId")

    # Validate environments
    project_ids = {p['projectId'] for p in data.get('projects', []) if p.get('projectId')}
    for i, env in enumerate(data.get('environments', [])):
        if not env.get('projectId'):
            errors.append(f"environments[{i}]: missing projectId")
        elif env['projectId'] not in project_ids:
            warnings.append(f"environments[{i}]: projectId '{env['projectId']}' not in projects list")
        if not env.get('envId'):
            errors.append(f"environments[{i}]: missing envId")

    # Validate clusters
    for i, cluster in enumerate(data.get('clusters', [])):
        if not cluster.get('clusterId'):
            errors.append(f"clusters[{i}]: missing clusterId")

    # Validate AWS accounts
    for i, account in enumerate(data.get('awsAccounts', [])):
        if not account.get('accountId'):
            errors.append(f"awsAccounts[{i}]: missing accountId")

    return len(errors) == 0, errors, warnings


# =============================================================================
# CLI Commands
# =============================================================================

@click.group('config')
def config_registry():
    """Config Registry management commands

    The Config Registry stores all runtime configuration:
    - Global settings (features, comparison groups)
    - Projects and their environments
    - EKS clusters
    - AWS accounts (cross-account roles)

    Use --direct flag to access DynamoDB directly (requires AWS credentials).
    Without --direct, commands use the Dashborion API (requires authentication).
    """
    pass


@config_registry.command('export')
@click.option('--output', '-o', default='-', help='Output file (- for stdout)')
@click.option('--direct', is_flag=True, help='Access DynamoDB directly instead of API')
@click.option('--table', '-t', 'table_name', help='DynamoDB table name (for --direct mode)')
@click.option('--profile', '-p', help='AWS profile (for --direct mode)')
@click.option('--region', '-r', help='AWS region (for --direct mode)')
@click.option('--pretty', is_flag=True, default=True, help='Pretty-print JSON output')
def export_config(output: str, direct: bool, table_name: Optional[str],
                  profile: Optional[str], region: Optional[str], pretty: bool):
    """Export Config Registry to JSON file

    Examples:

        # Export via API (requires authentication)
        dashborion config export -o config-backup.json

        # Export directly from DynamoDB
        dashborion config export --direct -t dashborion-rubix-config -o backup.json

        # Export to stdout
        dashborion config export --direct -t dashborion-rubix-config
    """
    try:
        if direct:
            if not table_name:
                raise click.ClickException("--table is required for --direct mode")
            click.echo(f"Exporting from DynamoDB table: {table_name}", err=True)
            data = _direct_export(table_name, profile, region)
        else:
            click.echo("Exporting via API...", err=True)
            data = _api_request('GET', '/api/config/export')

        # Output
        indent = 2 if pretty else None
        json_output = json.dumps(data, indent=indent, default=str, ensure_ascii=False)

        if output == '-':
            click.echo(json_output)
        else:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(json_output)
            click.echo(f"Exported to: {output}", err=True)
            click.echo(f"  Projects: {len(data.get('projects', []))}", err=True)
            click.echo(f"  Environments: {len(data.get('environments', []))}", err=True)
            click.echo(f"  Clusters: {len(data.get('clusters', []))}", err=True)
            click.echo(f"  AWS Accounts: {len(data.get('awsAccounts', []))}", err=True)

    except Exception as e:
        raise click.ClickException(f"Export failed: {e}")


@config_registry.command('import')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--mode', type=click.Choice(['merge', 'replace']), default='merge',
              help='Import mode: merge (update existing) or replace (delete all first)')
@click.option('--direct', is_flag=True, help='Access DynamoDB directly instead of API')
@click.option('--table', '-t', 'table_name', help='DynamoDB table name (for --direct mode)')
@click.option('--profile', '-p', help='AWS profile (for --direct mode)')
@click.option('--region', '-r', help='AWS region (for --direct mode)')
@click.option('--dry-run', is_flag=True, help='Validate only, do not import')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation for replace mode')
def import_config(input_file: str, mode: str, direct: bool, table_name: Optional[str],
                  profile: Optional[str], region: Optional[str], dry_run: bool, force: bool):
    """Import Config Registry from JSON file

    Examples:

        # Import via API (merge mode)
        dashborion config import config-backup.json

        # Import with replace (delete existing first)
        dashborion config import config.json --mode replace

        # Import directly to DynamoDB
        dashborion config import backup.json --direct -t dashborion-rubix-config

        # Validate without importing
        dashborion config import config.json --dry-run
    """
    try:
        # Load input file
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        click.echo(f"Loading: {input_file}", err=True)
        click.echo(f"  Projects: {len(data.get('projects', []))}", err=True)
        click.echo(f"  Environments: {len(data.get('environments', []))}", err=True)
        click.echo(f"  Clusters: {len(data.get('clusters', []))}", err=True)
        click.echo(f"  AWS Accounts: {len(data.get('awsAccounts', []))}", err=True)

        # Validate
        is_valid, errors, warnings = _validate_config(data)

        if errors:
            click.echo(click.style("\nValidation errors:", fg='red'), err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)

        if warnings:
            click.echo(click.style("\nWarnings:", fg='yellow'), err=True)
            for warning in warnings:
                click.echo(f"  - {warning}", err=True)

        if not is_valid:
            raise click.ClickException("Validation failed. Fix errors before importing.")

        if dry_run:
            click.echo(click.style("\nValidation passed!", fg='green'), err=True)
            return

        # Confirm replace mode
        if mode == 'replace' and not force:
            click.echo()
            click.confirm(
                click.style("WARNING: ", fg='red', bold=True) +
                "Replace mode will DELETE all existing config before importing. Continue?",
                abort=True
            )

        # Import
        actor = os.environ.get('USER', 'cli')
        if direct:
            if not table_name:
                raise click.ClickException("--table is required for --direct mode")
            click.echo(f"\nImporting to DynamoDB table: {table_name}", err=True)
            result = _direct_import(table_name, data, profile, region, mode, actor)
            imported = result
        else:
            click.echo("\nImporting via API...", err=True)
            data['mode'] = mode
            result = _api_request('POST', '/api/config/import', data)
            imported = result.get('imported', result)

        click.echo(click.style("\nImport complete!", fg='green', bold=True), err=True)
        click.echo(f"  Settings: {imported.get('settings', 0)}", err=True)
        click.echo(f"  Projects: {imported.get('projects', 0)}", err=True)
        click.echo(f"  Environments: {imported.get('environments', 0)}", err=True)
        click.echo(f"  Clusters: {imported.get('clusters', 0)}", err=True)
        click.echo(f"  AWS Accounts: {imported.get('awsAccounts', 0)}", err=True)

    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON file: {e}")
    except Exception as e:
        raise click.ClickException(f"Import failed: {e}")


@config_registry.command('migrate')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--output', '-o', help='Output file (if not specified, imports directly)')
@click.option('--direct', is_flag=True, help='Import directly to DynamoDB instead of API')
@click.option('--table', '-t', 'table_name', help='DynamoDB table name (for --direct mode)')
@click.option('--profile', '-p', help='AWS profile (for --direct mode)')
@click.option('--region', '-r', help='AWS region (for --direct mode)')
@click.option('--dry-run', is_flag=True, help='Convert and validate only, do not import')
def migrate_config(input_file: str, output: Optional[str], direct: bool, table_name: Optional[str],
                   profile: Optional[str], region: Optional[str], dry_run: bool):
    """Migrate from old infra.config.json format

    Converts the old format (projects, environments, crossAccountRoles)
    to the new Config Registry format.

    Examples:

        # Convert and output to file (for review)
        dashborion config migrate infra.config.json -o new-config.json

        # Convert and import via API
        dashborion config migrate infra.config.json

        # Convert and import directly to DynamoDB
        dashborion config migrate infra.config.json --direct -t dashborion-rubix-config

        # Dry run (convert and validate only)
        dashborion config migrate infra.config.json --dry-run
    """
    try:
        # Load old config
        with open(input_file, 'r', encoding='utf-8') as f:
            old_config = json.load(f)

        click.echo(f"Loading old config: {input_file}", err=True)

        # Show what will NOT be migrated
        not_migrated = []
        for key in ['mode', 'aws', 'managed', 'frontend', 'apiGateway', 'auth', 'naming', 'tags', 'ssm', 'configRegistry']:
            if key in old_config:
                not_migrated.append(key)

        if not_migrated:
            click.echo(click.style("\nThese settings will NOT be migrated (stay in infra.config.json):", fg='yellow'), err=True)
            for key in not_migrated:
                click.echo(f"  - {key}", err=True)

        # Convert
        click.echo("\nConverting to new format...", err=True)
        new_config = _migrate_infra_config(old_config)

        click.echo(f"  Projects: {len(new_config.get('projects', []))}", err=True)
        click.echo(f"  Environments: {len(new_config.get('environments', []))}", err=True)
        click.echo(f"  Clusters: {len(new_config.get('clusters', []))}", err=True)
        click.echo(f"  AWS Accounts: {len(new_config.get('awsAccounts', []))}", err=True)

        # Validate
        is_valid, errors, warnings = _validate_config(new_config)

        if errors:
            click.echo(click.style("\nValidation errors:", fg='red'), err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)

        if warnings:
            click.echo(click.style("\nWarnings:", fg='yellow'), err=True)
            for warning in warnings:
                click.echo(f"  - {warning}", err=True)

        if not is_valid:
            raise click.ClickException("Validation failed after conversion.")

        # Output to file
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=2, default=str, ensure_ascii=False)
            click.echo(f"\nConverted config saved to: {output}", err=True)
            return

        if dry_run:
            click.echo(click.style("\nConversion and validation passed!", fg='green'), err=True)
            return

        # Import
        actor = os.environ.get('USER', 'cli-migrate')
        if direct:
            if not table_name:
                raise click.ClickException("--table is required for --direct mode")
            click.echo(f"\nImporting to DynamoDB table: {table_name}", err=True)
            result = _direct_import(table_name, new_config, profile, region, 'merge', actor)
            imported = result
        else:
            click.echo("\nImporting via API...", err=True)
            result = _api_request('POST', '/api/config/migrate-from-json', old_config)
            imported = result.get('migrated', result)

        click.echo(click.style("\nMigration complete!", fg='green', bold=True), err=True)
        click.echo(f"  Settings: {imported.get('settings', 0)}", err=True)
        click.echo(f"  Projects: {imported.get('projects', 0)}", err=True)
        click.echo(f"  Environments: {imported.get('environments', 0)}", err=True)
        click.echo(f"  Clusters: {imported.get('clusters', 0)}", err=True)
        click.echo(f"  AWS Accounts: {imported.get('awsAccounts', 0)}", err=True)

    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON file: {e}")
    except Exception as e:
        raise click.ClickException(f"Migration failed: {e}")


@config_registry.command('validate')
@click.argument('input_file', type=click.Path(exists=True))
def validate_config_cmd(input_file: str):
    """Validate a config file without importing

    Examples:

        dashborion config validate config.json
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        click.echo(f"Validating: {input_file}")
        click.echo(f"  Projects: {len(data.get('projects', []))}")
        click.echo(f"  Environments: {len(data.get('environments', []))}")
        click.echo(f"  Clusters: {len(data.get('clusters', []))}")
        click.echo(f"  AWS Accounts: {len(data.get('awsAccounts', []))}")

        is_valid, errors, warnings = _validate_config(data)

        if errors:
            click.echo(click.style("\nErrors:", fg='red'))
            for error in errors:
                click.echo(f"  - {error}")

        if warnings:
            click.echo(click.style("\nWarnings:", fg='yellow'))
            for warning in warnings:
                click.echo(f"  - {warning}")

        if is_valid:
            click.echo(click.style("\nValidation passed!", fg='green', bold=True))
        else:
            click.echo(click.style("\nValidation failed!", fg='red', bold=True))
            sys.exit(1)

    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON file: {e}")


@config_registry.command('show')
@click.option('--direct', is_flag=True, help='Access DynamoDB directly instead of API')
@click.option('--table', '-t', 'table_name', help='DynamoDB table name (for --direct mode)')
@click.option('--profile', '-p', help='AWS profile (for --direct mode)')
@click.option('--region', '-r', help='AWS region (for --direct mode)')
@click.option('--output', '-o', type=click.Choice(['summary', 'json']), default='summary',
              help='Output format')
def show_config(direct: bool, table_name: Optional[str], profile: Optional[str],
                region: Optional[str], output: str):
    """Show current Config Registry content

    Examples:

        # Show summary via API
        dashborion config show

        # Show full JSON via API
        dashborion config show -o json

        # Show directly from DynamoDB
        dashborion config show --direct -t dashborion-rubix-config
    """
    try:
        if direct:
            if not table_name:
                raise click.ClickException("--table is required for --direct mode")
            data = _direct_export(table_name, profile, region)
        else:
            data = _api_request('GET', '/api/config/export')

        if output == 'json':
            click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))
            return

        # Summary output
        click.echo(click.style("Config Registry Summary", fg='cyan', bold=True))
        click.echo()

        # Settings
        settings = data.get('settings') or {}
        features = settings.get('features', {})
        enabled_features = [k for k, v in features.items() if v]
        click.echo(f"Settings:")
        click.echo(f"  Features: {', '.join(enabled_features) if enabled_features else 'none'}")
        click.echo()

        # Projects
        projects = data.get('projects', [])
        click.echo(f"Projects ({len(projects)}):")
        for p in projects:
            status = p.get('status', 'active')
            status_color = 'green' if status == 'active' else 'yellow'
            click.echo(f"  - {p.get('projectId')}: {p.get('displayName', '')} "
                       f"[{click.style(status, fg=status_color)}]")

        # Environments
        envs = data.get('environments', [])
        click.echo(f"\nEnvironments ({len(envs)}):")
        # Group by project
        by_project = {}
        for e in envs:
            pid = e.get('projectId', 'unknown')
            if pid not in by_project:
                by_project[pid] = []
            by_project[pid].append(e)

        for pid, project_envs in by_project.items():
            click.echo(f"  {pid}:")
            for e in project_envs:
                status = e.get('status', 'active')
                enabled = e.get('enabled', True)
                if not enabled:
                    status_str = click.style('disabled', fg='red')
                elif status == 'active' or status == 'deployed':
                    status_str = click.style(status, fg='green')
                else:
                    status_str = click.style(status, fg='yellow')
                click.echo(f"    - {e.get('envId')}: {e.get('displayName', '')} [{status_str}]")

        # Clusters
        clusters = data.get('clusters', [])
        click.echo(f"\nClusters ({len(clusters)}):")
        for c in clusters:
            click.echo(f"  - {c.get('clusterId')}: {c.get('name', '')} ({c.get('region', '')})")

        # AWS Accounts
        accounts = data.get('awsAccounts', [])
        click.echo(f"\nAWS Accounts ({len(accounts)}):")
        for a in accounts:
            click.echo(f"  - {a.get('accountId')}: {a.get('displayName', '')} ({a.get('defaultRegion', '')})")

    except Exception as e:
        raise click.ClickException(f"Failed to show config: {e}")


# =============================================================================
# Local CLI Config (moved from main.py)
# =============================================================================

@config_registry.command('local')
@click.pass_context
def local_config(ctx):
    """Show current CLI configuration (profile, region, etc.)

    This shows the local CLI settings, not the Config Registry.

    Examples:

        dashborion config local
    """
    # Import here to avoid circular imports
    from dashborion.utils.output import OutputFormatter

    # Get parent context (DashborionContext)
    dashborion_ctx = ctx.find_root().obj
    if dashborion_ctx is None:
        click.echo("No context available", err=True)
        return

    formatter = OutputFormatter(dashborion_ctx.output_format if hasattr(dashborion_ctx, 'output_format') else 'table')

    config = dashborion_ctx.config if hasattr(dashborion_ctx, 'config') and dashborion_ctx.config else {}

    config_info = {
        'profile': (dashborion_ctx.profile if hasattr(dashborion_ctx, 'profile') else None) or config.get('default_profile', 'default'),
        'region': (dashborion_ctx.region if hasattr(dashborion_ctx, 'region') else None) or config.get('default_region', 'eu-west-3'),
        'environments': list(config.get('environments', {}).keys()),
        'config_file': config.get('_config_path', 'not loaded'),
    }

    formatter.output(config_info, title="CLI Configuration")


# Alias for backwards compatibility
config = config_registry
