#!/bin/bash
# Seed LocalStack DynamoDB with sample config data for local development
#
# Usage: ./scripts/seed-localstack.sh
# Requires: awslocal (pip install awscli-local) or aws cli with endpoint-url

set -e

ENDPOINT_URL="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-eu-west-3}"
CONFIG_TABLE="dashborion-local-config"
STATE_TABLE="dashborion-local-state"

# Use awslocal if available, otherwise aws with endpoint-url
if command -v awslocal &> /dev/null; then
    AWS_CMD="awslocal"
else
    AWS_CMD="aws --endpoint-url $ENDPOINT_URL --region $REGION"
fi

echo "Seeding LocalStack DynamoDB at $ENDPOINT_URL..."

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
for i in {1..30}; do
    if curl -s "$ENDPOINT_URL/_localstack/health" | grep -q '"dynamodb"'; then
        echo "LocalStack is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Check if tables exist (they should be created by SST deploy)
echo "Checking tables..."
$AWS_CMD dynamodb describe-table --table-name $CONFIG_TABLE > /dev/null 2>&1 || {
    echo "Error: Table $CONFIG_TABLE not found. Run 'npx sst deploy --stage local' first."
    exit 1
}

# Seed GLOBAL settings
echo "Seeding GLOBAL#settings..."
$AWS_CMD dynamodb put-item --table-name $CONFIG_TABLE --item '{
    "pk": {"S": "GLOBAL"},
    "sk": {"S": "settings"},
    "features": {"M": {
        "pipelines": {"BOOL": false},
        "comparison": {"BOOL": true},
        "refresh": {"BOOL": false},
        "admin": {"BOOL": true}
    }},
    "comparison": {"M": {
        "groups": {"L": [
            {"M": {"prefix": {"S": "legacy-"}, "label": {"S": "Legacy"}, "role": {"S": "source"}}},
            {"M": {"prefix": {"S": "nh-"}, "label": {"S": "New Horizon"}, "role": {"S": "destination"}}}
        ]},
        "refreshThresholdSeconds": {"N": "300"}
    }},
    "updatedAt": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
    "updatedBy": {"S": "seed-script"},
    "version": {"N": "1"}
}'

# Seed sample project
echo "Seeding PROJECT#demo-project..."
$AWS_CMD dynamodb put-item --table-name $CONFIG_TABLE --item '{
    "pk": {"S": "PROJECT"},
    "sk": {"S": "demo-project"},
    "projectId": {"S": "demo-project"},
    "displayName": {"S": "Demo Project"},
    "description": {"S": "Sample project for local development"},
    "status": {"S": "active"},
    "features": {"M": {
        "pipelines": {"BOOL": false},
        "comparison": {"BOOL": true}
    }},
    "services": {"L": [
        {"S": "api"},
        {"S": "web"},
        {"S": "worker"}
    ]},
    "envColors": {"M": {
        "dev": {"S": "#10B981"},
        "staging": {"S": "#F59E0B"},
        "production": {"S": "#EF4444"}
    }},
    "serviceNaming": {"M": {
        "prefix": {"S": "demo"}
    }},
    "aws": {"M": {
        "accounts": {"M": {
            "dev": {"S": "000000000000"},
            "staging": {"S": "000000000000"},
            "production": {"S": "000000000000"}
        }}
    }},
    "updatedAt": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
    "updatedBy": {"S": "seed-script"},
    "version": {"N": "1"}
}'

# Seed sample environments
for env in dev staging production; do
    echo "Seeding ENV#demo-project#$env..."
    $AWS_CMD dynamodb put-item --table-name $CONFIG_TABLE --item '{
        "pk": {"S": "ENV"},
        "sk": {"S": "demo-project#'$env'"},
        "projectId": {"S": "demo-project"},
        "envId": {"S": "'$env'"},
        "displayName": {"S": "'${env^}'"},
        "accountId": {"S": "000000000000"},
        "region": {"S": "eu-west-3"},
        "status": {"S": "deployed"},
        "enabled": {"BOOL": true},
        "orchestratorType": {"S": "ecs"},
        "infrastructure": {"M": {
            "resources": {"M": {}}
        }},
        "updatedAt": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
        "updatedBy": {"S": "seed-script"},
        "version": {"N": "1"}
    }'
done

# Seed sample AWS account
echo "Seeding GLOBAL#aws-account:000000000000..."
$AWS_CMD dynamodb put-item --table-name $CONFIG_TABLE --item '{
    "pk": {"S": "GLOBAL"},
    "sk": {"S": "aws-account:000000000000"},
    "accountId": {"S": "000000000000"},
    "displayName": {"S": "Local Account"},
    "defaultRegion": {"S": "eu-west-3"},
    "updatedAt": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
    "updatedBy": {"S": "seed-script"}
}'

echo ""
echo "Done! LocalStack seeded with sample data."
echo ""
echo "Config table: $CONFIG_TABLE"
echo "State table: $STATE_TABLE"
echo ""
echo "You can now:"
echo "  1. Start the frontend: cd packages/frontend && npm run dev"
echo "  2. The API is available at the URL printed by 'npx sst deploy --stage local'"
