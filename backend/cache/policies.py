"""
Cache policies and TTLs for infrastructure resources.
"""

RESOURCE_TTLS_SECONDS = {
    "cloudfront": 120,
    "alb": 60,
    "rds": 120,
    "redis": 120,
    "s3": 300,
    "network": 300,
    "workloads": 30,
    "efs": 300,
    "routing": 300,
    "enis": 120,
    "security-group": 300,
    "nodes": 30,
    "k8s-services": 60,
    "ingresses": 60,
    "namespaces": 300,
    "meta": 600,
}


def get_ttl(resource: str, default: int = 60) -> int:
    return RESOURCE_TTLS_SECONDS.get(resource, default)
