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

### Admin Commands

Manage users, groups, and permissions. Requires admin role.

#### Users

```bash
# List all users
dashborion admin user list

# Show user details
dashborion admin user show user@example.com

# Create a new user
dashborion admin user create user@example.com --role viewer
dashborion admin user create admin@example.com --role admin

# Update user role
dashborion admin user update user@example.com --role operator

# Disable/enable a user
dashborion admin user update user@example.com --disable
dashborion admin user update user@example.com --enable

# Delete a user
dashborion admin user delete user@example.com
```

#### Groups

```bash
# List all groups
dashborion admin group list

# Create a local group
dashborion admin group create platform-team --description "Platform engineers"

# Create a group mapped to SSO
dashborion admin group create viewers --sso-group-name "dashborion-viewers" --role viewer

# Add/remove users from groups
dashborion admin group add-user platform-team user@example.com
dashborion admin group remove-user platform-team user@example.com

# Show group members
dashborion admin group members platform-team

# Delete a group
dashborion admin group delete platform-team
```

#### Permissions

```bash
# List user permissions
dashborion admin permission list user@example.com

# Grant permission to a user
dashborion admin permission grant user@example.com \
  --project homebox \
  --environment staging \
  --role operator

# Grant global admin
dashborion admin permission grant admin@example.com \
  --project "*" \
  --environment "*" \
  --role admin

# Revoke permission
dashborion admin permission revoke user@example.com \
  --project homebox \
  --environment staging

# Grant permission to a group
dashborion admin permission grant-group platform-team \
  --project homebox \
  --environment "*" \
  --role operator
```

#### Role Hierarchy

| Role | Permissions |
|------|-------------|
| `viewer` | Read-only access (view services, logs, infrastructure) |
| `operator` | Viewer + deploy, restart, scale services |
| `admin` | Operator + manage users, groups, permissions |

#### Bootstrap

The first user to authenticate via SSO automatically becomes a global admin.
Subsequent users are created with `viewer` role by default.

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

### Dashborion Authentication (Recommended)

Authenticate with the Dashborion backend for full feature access:

```bash
# Device Flow - Opens browser for SSO authentication
dashborion auth login

# AWS SSO - Reuse existing AWS SSO session (exchanges for Dashborion token)
dashborion auth login --use-sso

# Check authentication status
dashborion auth whoami
dashborion auth status

# Logout
dashborion auth logout
```

Credentials are stored in `~/.dashborion/credentials.json`.

### SigV4 Authentication (AWS Identity)

Use AWS credentials directly without storing tokens. Uses Vault-style STS identity proof:

```bash
# Use --sigv4 flag with any command
dashborion --sigv4 auth whoami
dashborion --sigv4 services list --env staging

# With specific AWS profile
AWS_PROFILE=my-sso-profile dashborion --sigv4 services list
```

**How it works:**
1. CLI signs a GetCallerIdentity request with your AWS credentials
2. Signed request is sent to the server in HTTP headers
3. Server forwards to AWS STS for identity verification
4. Email is extracted from Identity Center session name (e.g., `AWSReservedSSO_.../user@example.com`)

**Requirements:**
- AWS credentials (via `aws sso login`, IAM user, or assumed role)
- User must exist in Dashborion with matching email
- Works with HTTP API v2 (no AWS_IAM auth type required)

### AWS Profile Authentication (Legacy)

For direct AWS API access without the Dashborion backend:

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
| `DASHBORION_API_URL` | Dashborion API URL (for auth) |
| `CONFLUENCE_URL` | Confluence base URL |
| `CONFLUENCE_USERNAME` | Confluence username |
| `CONFLUENCE_TOKEN` | Confluence API token |

## License

MIT License - see [LICENSE](../LICENSE) for details.
