"""Components and relations configuration"""

# Composants par défaut à surveiller
DEFAULT_COMPONENTS = [
    'apache',        # Service apache
    'haproxy',      # Service haproxy
    'hybris-fo',    # Service hybris-fo
    'hybris-bo',    # Service hybris-bo
    'nextjs',       # Service nextjs
    'sftp',         # Service sftp
    'solr-leader',  # Service solr-leader
    'solr-follower' # Service solr-follower
]

# Configuration des relations entre services
SERVICE_RELATIONS = {
    'apache': {
        'targets': ['nextjs', 'haproxy'],
        'style': {'color': 'green', 'style': 'solid'}
    },
    'nextjs': {
        'targets': ['haproxy'],
        'style': {'color': 'green', 'style': 'solid'}
    },
    'haproxy': {
        'targets': ['hybris-fo'],
        'style': {'color': 'red', 'style': 'solid'}
    },
    'hybris-fo': {
        'style': {'color': 'purple', 'style': 'solid'}
    },
    'hybris-bo': {
        'style': {'color': 'purple', 'style': 'solid'}
    }
}