"""Global diagram configuration."""

# Connexion style
EDGE_STYLES = {
    'ingress': {"color": "blue", "style": "bold"},
    'web': {"color": "green", "style": "solid"},
    'app': {"color": "red", "style": "solid"},
    'db': {"color": "purple", "style": "solid"},
    'lambda': {"color": "orange", "style": "dashed"}
}

# Graph attributes
GRAPH_ATTR = {
    "splines": "ortho",
    "nodesep": "2.0",
    "ranksep": "2.0",
    "pad": "3.0",
    "rankdir": "LR",
    #"ordering": "in"
}

# AWS configuration
AWS_DEFAULT_REGION = 'eu-central-1'