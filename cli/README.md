# Dashborion CLI

Command-line interface for the Dashborion infrastructure dashboard.

## Installation

### Via pip

```bash
pip install dashborion-cli
```

### Via Homebrew (macOS/Linux)

```bash
brew tap KamorionLabs/tap
brew install dashborion-cli
```

### Development Installation

```bash
git clone https://github.com/KamorionLabs/dashborion.git
cd dashborion/cli
pip install -e ".[dev]"
```

## Quick Start

1. Create a configuration file `~/.dashborion/config.yaml`:

```yaml
default_profile: myprofile
default_region: eu-west-3

environments:
  staging:
    type: ecs
    cluster: my-staging-cluster
    aws_profile: my-staging-profile

  production:
    type: ecs
    cluster: my-production-cluster
    aws_profile: my-production-profile
```

2. Run commands:

```bash
# List services
dashborion services list --env staging

# Show infrastructure
dashborion infra show --env production

# Generate diagram
dashborion diagram generate --env staging --output architecture.png
```

## Commands

### Services

```bash
# List all services
dashborion services list --env staging

# Describe a service
dashborion services describe backend --env production

# View tasks/pods
dashborion services tasks backend --env staging

# Stream logs
dashborion services logs backend --env staging --follow

# Force deploy
dashborion services deploy backend --env staging --force
```

### Infrastructure

```bash
# Show all infrastructure
dashborion infra show --env staging

# Show specific resources
dashborion infra alb --env production
dashborion infra rds --env production
dashborion infra redis --env staging
dashborion infra cloudfront --env production

# Network topology
dashborion infra network --env staging
```

### Kubernetes (EKS)

```bash
# List pods
dashborion k8s pods --context my-eks-cluster --namespace staging

# List services
dashborion k8s services --context my-eks-cluster -A

# List deployments
dashborion k8s deployments --context my-eks-cluster -n default

# View pod logs
dashborion k8s logs my-pod --context my-eks-cluster -n staging -f
```

### Pipelines

```bash
# List pipelines
dashborion pipelines list --env staging

# Show pipeline status
dashborion pipelines status my-build-pipeline

# Trigger pipeline
dashborion pipelines trigger my-deploy-pipeline --wait

# List ECR images
dashborion pipelines images backend --env staging
```

### Diagrams

```bash
# Generate from environment config
dashborion diagram generate --env staging --output architecture.png

# Generate from YAML config
dashborion diagram generate --config diagrams.yaml

# Publish to Confluence
dashborion diagram publish --file architecture.png --confluence-page 12345
```

## Output Formats

All commands support multiple output formats:

```bash
# Table format (default)
dashborion services list --env staging

# JSON format
dashborion services list --env staging --output json

# YAML format
dashborion services list --env staging --output yaml
```

## Authentication

The CLI uses AWS credentials from your configured profiles:

```bash
# Use specific profile
dashborion services list --env staging --profile my-profile

# Use default profile
dashborion services list --env staging
```

Configure profiles in `~/.aws/credentials` or use AWS SSO:

```bash
aws configure sso
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_PROFILE` | Default AWS profile |
| `AWS_REGION` | Default AWS region |
| `DASHBORION_CONFIG` | Path to config file |
| `CONFLUENCE_URL` | Confluence base URL |
| `CONFLUENCE_USERNAME` | Confluence username |
| `CONFLUENCE_TOKEN` | Confluence API token |

## License

MIT License - see [LICENSE](../LICENSE) for details.
