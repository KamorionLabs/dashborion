#!/usr/bin/env python3
"""
Migration script: Convert ENV items to new infrastructure format.

Legacy sources:
- kubernetes.clusterName, kubernetes.namespace
- discoveryTags (flat) or infrastructure.discoveryTags
- databases/caches (legacy)
- checkers.* identifiers/tags

New format:
- clusterName, namespace (flat)
- infrastructure.defaultTags
- infrastructure.domainConfig (if present)
- infrastructure.resources.<type>.ids / tags
"""

import boto3
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List


def _merge_ids(resource_cfg: Dict[str, Any], ids: List[str]) -> Dict[str, Any]:
    if not ids:
        return resource_cfg
    existing = resource_cfg.get("ids") or []
    merged = list(dict.fromkeys(existing + ids))
    resource_cfg["ids"] = merged
    return resource_cfg


def _merge_tags(resource_cfg: Dict[str, Any], tags: Dict[str, str]) -> Dict[str, Any]:
    if not tags:
        return resource_cfg
    merged = {**(resource_cfg.get("tags") or {}), **tags}
    resource_cfg["tags"] = merged
    return resource_cfg


def _extract_infra(item: Dict[str, Any]) -> Dict[str, Any]:
    infra = item.get("infrastructure") if isinstance(item.get("infrastructure"), dict) else {}
    infra = infra.copy()

    default_tags = infra.get("defaultTags") or infra.get("discoveryTags") or item.get("discoveryTags") or {}
    domain_config = infra.get("domainConfig") or item.get("domainConfig") or {}
    resources = infra.get("resources") if isinstance(infra.get("resources"), dict) else {}

    resources = {k: (v or {}).copy() for k, v in resources.items() if isinstance(v, dict)}

    checkers = item.get("checkers") if isinstance(item.get("checkers"), dict) else {}
    rds_ids = []
    for key in ("rdsClusterIdentifier", "rdsInstanceIdentifier", "rdsIdentifier"):
        if checkers.get(key):
            rds_ids.append(checkers.get(key))
    if isinstance(checkers.get("rdsIdentifiers"), list):
        rds_ids.extend(checkers.get("rdsIdentifiers"))

    efs_ids = []
    if checkers.get("efsFileSystemId"):
        efs_ids.append(checkers.get("efsFileSystemId"))
    if isinstance(checkers.get("efsFileSystemIds"), list):
        efs_ids.extend(checkers.get("efsFileSystemIds"))

    tag_mappings = {
        "albTags": "alb",
        "cloudfrontTags": "cloudfront",
        "sgTags": "network",
    }

    if rds_ids:
        resources["rds"] = _merge_ids(resources.get("rds", {}), rds_ids)
    if efs_ids:
        resources["efs"] = _merge_ids(resources.get("efs", {}), efs_ids)
    for tag_key, resource_key in tag_mappings.items():
        tags = checkers.get(tag_key)
        if isinstance(tags, dict) and tags:
            resources[resource_key] = _merge_tags(resources.get(resource_key, {}), tags)

    # Clean infra object (remove legacy keys, keep extra custom keys)
    infra.pop("discoveryTags", None)
    infra.pop("databases", None)
    infra.pop("caches", None)

    if default_tags:
        infra["defaultTags"] = default_tags
    else:
        infra.pop("defaultTags", None)

    if domain_config:
        infra["domainConfig"] = domain_config
    else:
        infra.pop("domainConfig", None)

    if resources:
        infra["resources"] = resources
    else:
        infra.pop("resources", None)

    return infra


def migrate_table(table_name: str, profile: str, region: str, dry_run: bool = True):
    """Migrate all ENV items in a table to new format."""

    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table(table_name)

    # Scan all ENV items
    response = table.scan(
        FilterExpression='pk = :pk',
        ExpressionAttributeValues={':pk': 'ENV'}
    )

    items = response.get('Items', [])
    print(f"\nFound {len(items)} ENV items in {table_name}")

    migrated = 0
    skipped = 0

    for item in items:
        sk = item.get('sk', '')
        env_id = item.get('envId', '')
        project_id = item.get('projectId', '')

        kubernetes = item.get('kubernetes', {}) if isinstance(item.get('kubernetes'), dict) else {}
        cluster_name = item.get('clusterName') or kubernetes.get('clusterName', '')
        namespace = item.get('namespace') or kubernetes.get('namespace', '')

        infra = _extract_infra(item)

        new_item = item.copy()
        new_item['projectId'] = project_id
        new_item['envId'] = env_id
        new_item['displayName'] = item.get('displayName', env_id)
        new_item['accountId'] = item.get('accountId', '')
        new_item['region'] = item.get('region', 'eu-central-1')
        new_item['clusterName'] = cluster_name
        new_item['namespace'] = namespace
        new_item['services'] = item.get('services', [])
        new_item['infrastructure'] = infra
        new_item['updatedAt'] = datetime.now(timezone.utc).isoformat()
        new_item['updatedBy'] = 'migration-script'
        new_item['version'] = item.get('version', 0) + 1

        # Remove legacy fields
        new_item.pop('kubernetes', None)
        new_item.pop('discoveryTags', None)
        new_item.pop('databases', None)
        new_item.pop('caches', None)
        new_item.pop('domainConfig', None)

        print(f"  MIGRATE {sk}")
        print(f"    clusterName: {cluster_name}")
        print(f"    namespace: {namespace}")
        print(f"    services: {new_item.get('services', [])}")
        print(f"    infrastructure: {infra}")

        if not dry_run:
            table.put_item(Item=new_item)
            print(f"    -> DONE")
        else:
            print(f"    -> DRY RUN (not saved)")

        migrated += 1

    print(f"\nSummary for {table_name}:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")

    return migrated, skipped


def main():
    parser = argparse.ArgumentParser(description='Migrate ENV items to new format')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Dry run (default)')
    parser.add_argument('--execute', action='store_true', help='Actually execute the migration')
    parser.add_argument('--rubix-only', action='store_true', help='Only migrate Rubix')
    parser.add_argument('--homebox-only', action='store_true', help='Only migrate Homebox')
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("Use --execute to actually migrate")
        print("=" * 60)
    else:
        print("=" * 60)
        print("EXECUTE MODE - Changes will be saved to DynamoDB")
        print("=" * 60)

    total_migrated = 0
    total_skipped = 0

    # Rubix
    if not args.homebox_only:
        print("\n" + "=" * 60)
        print("RUBIX (shared-services)")
        print("=" * 60)
        m, s = migrate_table(
            table_name='ddb-dashborion-shared-config',
            profile='shared-services/AWSAdministratorAccess',
            region='eu-central-1',
            dry_run=dry_run
        )
        total_migrated += m
        total_skipped += s

    # Homebox
    if not args.rubix_only:
        print("\n" + "=" * 60)
        print("HOMEBOX (homebox-shared-services)")
        print("=" * 60)
        m, s = migrate_table(
            table_name='dashborion-homebox-config',
            profile='homebox-shared-services/AdministratorAccess',
            region='eu-west-3',
            dry_run=dry_run
        )
        total_migrated += m
        total_skipped += s

    print("\n" + "=" * 60)
    print(f"TOTAL: Migrated {total_migrated}, Skipped {total_skipped}")
    print("=" * 60)


if __name__ == '__main__':
    main()
