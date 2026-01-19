#!/bin/bash
# Setup LocalStack for Dashborion local development
# Creates DynamoDB tables and seeds sample data WITHOUT SST deploy
#
# This script is the recommended way to set up LocalStack because:
# - SST v3 requires ECR which is a LocalStack Pro feature
# - This script creates everything needed using awslocal/aws CLI
#
# Usage: ./scripts/setup-localstack.sh
# Requires: awslocal (pip install awscli-local) or aws cli

set -e

ENDPOINT_URL="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-eu-west-3}"

# Table names (must match naming.table() in infra/naming.ts for stage=local)
TABLE_PREFIX="dashborion-local"

# Determine AWS command to use
if command -v awslocal &> /dev/null; then
    aws_cmd() { awslocal "$@"; }
else
    # Set dummy credentials for LocalStack
    export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
    export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
    aws_cmd() { aws --endpoint-url "$ENDPOINT_URL" --region "$REGION" "$@"; }
fi

echo "=============================================="
echo "Setting up LocalStack for Dashborion"
echo "=============================================="
echo "Endpoint: $ENDPOINT_URL"
echo "Region: $REGION"
echo ""

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
for i in {1..30}; do
    if curl -s "$ENDPOINT_URL/_localstack/health" | grep -q '"dynamodb"'; then
        echo "LocalStack is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: LocalStack did not become ready in time"
        exit 1
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done
echo ""

# Function to create table if it doesn't exist
create_simple_table() {
    local table_name=$1
    local has_ttl=$2

    if aws_cmd dynamodb describe-table --table-name "$table_name" > /dev/null 2>&1; then
        echo "Table $table_name already exists, skipping..."
    else
        echo "Creating table $table_name..."
        aws_cmd dynamodb create-table \
            --table-name "$table_name" \
            --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
            --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
            --billing-mode PAY_PER_REQUEST

        if [ "$has_ttl" = "true" ]; then
            aws_cmd dynamodb update-time-to-live --table-name "$table_name" \
                --time-to-live-specification Enabled=true,AttributeName=ttl 2>/dev/null || true
        fi
    fi
}

create_table_with_gsi() {
    local table_name=$1
    local gsi_name=$2
    local gsi_pk=$3
    local gsi_sk=$4
    local has_ttl=$5

    if aws_cmd dynamodb describe-table --table-name "$table_name" > /dev/null 2>&1; then
        echo "Table $table_name already exists, skipping..."
    else
        echo "Creating table $table_name with GSI $gsi_name..."
        aws_cmd dynamodb create-table \
            --table-name "$table_name" \
            --attribute-definitions \
                AttributeName=pk,AttributeType=S \
                AttributeName=sk,AttributeType=S \
                AttributeName="$gsi_pk",AttributeType=S \
                AttributeName="$gsi_sk",AttributeType=S \
            --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
            --global-secondary-indexes "[{
                \"IndexName\":\"$gsi_name\",
                \"KeySchema\":[
                    {\"AttributeName\":\"$gsi_pk\",\"KeyType\":\"HASH\"},
                    {\"AttributeName\":\"$gsi_sk\",\"KeyType\":\"RANGE\"}
                ],
                \"Projection\":{\"ProjectionType\":\"ALL\"}
            }]" \
            --billing-mode PAY_PER_REQUEST

        if [ "$has_ttl" = "true" ]; then
            aws_cmd dynamodb update-time-to-live --table-name "$table_name" \
                --time-to-live-specification Enabled=true,AttributeName=ttl 2>/dev/null || true
        fi
    fi
}

create_config_table() {
    local table_name=$1

    if aws_cmd dynamodb describe-table --table-name "$table_name" > /dev/null 2>&1; then
        echo "Table $table_name already exists, skipping..."
    else
        echo "Creating table $table_name with GSI project-index..."
        aws_cmd dynamodb create-table \
            --table-name "$table_name" \
            --attribute-definitions \
                AttributeName=pk,AttributeType=S \
                AttributeName=sk,AttributeType=S \
                AttributeName=projectId,AttributeType=S \
            --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
            --global-secondary-indexes "[{
                \"IndexName\":\"project-index\",
                \"KeySchema\":[
                    {\"AttributeName\":\"projectId\",\"KeyType\":\"HASH\"},
                    {\"AttributeName\":\"sk\",\"KeyType\":\"RANGE\"}
                ],
                \"Projection\":{\"ProjectionType\":\"ALL\"}
            }]" \
            --billing-mode PAY_PER_REQUEST
    fi
}

echo "Creating DynamoDB tables..."
echo ""

# Create tables
create_simple_table "${TABLE_PREFIX}-tokens" true
create_simple_table "${TABLE_PREFIX}-device-codes" true
create_table_with_gsi "${TABLE_PREFIX}-users" "role-index" "gsi1pk" "gsi1sk" false
create_table_with_gsi "${TABLE_PREFIX}-groups" "sso-group-index" "gsi1pk" "gsi1sk" false
create_table_with_gsi "${TABLE_PREFIX}-permissions" "project-env-index" "gsi1pk" "gsi1sk" true
create_table_with_gsi "${TABLE_PREFIX}-audit" "action-index" "gsi1pk" "gsi1sk" true
create_config_table "${TABLE_PREFIX}-config"
create_simple_table "${TABLE_PREFIX}-cache" true

echo ""
echo "All tables created!"
echo ""

# Seed sample data
CONFIG_TABLE="${TABLE_PREFIX}-config"
USERS_TABLE="${TABLE_PREFIX}-users"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "Seeding sample data..."
echo ""

# Seed GLOBAL settings
echo "  - GLOBAL#settings"
aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
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
    "updatedAt": {"S": "'"$TIMESTAMP"'"},
    "updatedBy": {"S": "setup-script"},
    "version": {"N": "1"}
}'

# Seed sample project
echo "  - PROJECT#demo-project"
aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
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
    "updatedAt": {"S": "'"$TIMESTAMP"'"},
    "updatedBy": {"S": "setup-script"},
    "version": {"N": "1"}
}'

# Seed demo-project environments (ECS)
for env in dev staging production; do
    echo "  - ENV#demo-project#$env"
    display_name="$(echo ${env:0:1} | tr '[:lower:]' '[:upper:]')${env:1}"
    cluster_name="demo-${env}-cluster"
    aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
        "pk": {"S": "ENV"},
        "sk": {"S": "demo-project#'"$env"'"},
        "projectId": {"S": "demo-project"},
        "envId": {"S": "'"$env"'"},
        "displayName": {"S": "'"$display_name"'"},
        "accountId": {"S": "000000000000"},
        "region": {"S": "eu-west-3"},
        "status": {"S": "deployed"},
        "enabled": {"BOOL": true},
        "orchestratorType": {"S": "ecs"},
        "clusterName": {"S": "'"$cluster_name"'"},
        "infrastructure": {"M": {
            "resources": {"M": {}}
        }},
        "updatedAt": {"S": "'"$TIMESTAMP"'"},
        "updatedBy": {"S": "setup-script"},
        "version": {"N": "1"}
    }'
done

# Seed demo-eks project
echo "  - PROJECT#demo-eks"
aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
    "pk": {"S": "PROJECT"},
    "sk": {"S": "demo-eks"},
    "projectId": {"S": "demo-eks"},
    "displayName": {"S": "Demo EKS"},
    "description": {"S": "Sample EKS project for local development"},
    "status": {"S": "active"},
    "features": {"M": {
        "pipelines": {"BOOL": false},
        "comparison": {"BOOL": true}
    }},
    "services": {"L": [
        {"S": "frontend"},
        {"S": "backend"},
        {"S": "worker"}
    ]},
    "envColors": {"M": {
        "dev": {"S": "#10B981"},
        "staging": {"S": "#F59E0B"},
        "production": {"S": "#EF4444"}
    }},
    "serviceNaming": {"M": {
        "prefix": {"S": "eks-demo"}
    }},
    "aws": {"M": {
        "accounts": {"M": {
            "dev": {"S": "000000000000"},
            "staging": {"S": "000000000000"},
            "production": {"S": "000000000000"}
        }}
    }},
    "updatedAt": {"S": "'"$TIMESTAMP"'"},
    "updatedBy": {"S": "setup-script"},
    "version": {"N": "1"}
}'

# Seed demo-eks environments
for env in dev staging production; do
    echo "  - ENV#demo-eks#$env"
    display_name="$(echo ${env:0:1} | tr '[:lower:]' '[:upper:]')${env:1}"
    cluster_name="eks-demo-${env}"
    namespace="demo-${env}"
    aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
        "pk": {"S": "ENV"},
        "sk": {"S": "demo-eks#'"$env"'"},
        "projectId": {"S": "demo-eks"},
        "envId": {"S": "'"$env"'"},
        "displayName": {"S": "'"$display_name"'"},
        "accountId": {"S": "000000000000"},
        "region": {"S": "eu-west-3"},
        "status": {"S": "deployed"},
        "enabled": {"BOOL": true},
        "orchestratorType": {"S": "eks"},
        "clusterName": {"S": "'"$cluster_name"'"},
        "namespace": {"S": "'"$namespace"'"},
        "infrastructure": {"M": {
            "resources": {"M": {}}
        }},
        "updatedAt": {"S": "'"$TIMESTAMP"'"},
        "updatedBy": {"S": "setup-script"},
        "version": {"N": "1"}
    }'
done

# Seed sample AWS account
echo "  - GLOBAL#aws-account:000000000000"
aws_cmd dynamodb put-item --table-name "$CONFIG_TABLE" --item '{
    "pk": {"S": "GLOBAL"},
    "sk": {"S": "aws-account:000000000000"},
    "accountId": {"S": "000000000000"},
    "displayName": {"S": "Local Account"},
    "defaultRegion": {"S": "eu-west-3"},
    "updatedAt": {"S": "'"$TIMESTAMP"'"},
    "updatedBy": {"S": "setup-script"}
}'

# Seed admin user (password: admin)
# Hash generated with PBKDF2-SHA256, 260000 iterations
# Schema: pk=USER#{email}, sk=PROFILE (as expected by user_management.py)
ADMIN_PASSWORD_HASH="pbkdf2:sha256:260000\$localdev1234567890abcdef\$e77771d6c26d78841ff9be8ef0f863a762220b60b87774f06ffc05ad37dc5939"
ADMIN_TIMESTAMP=$(date +%s)
echo "  - USER#admin@localhost (password: admin)"
aws_cmd dynamodb put-item --table-name "$USERS_TABLE" --item '{
    "pk": {"S": "USER#admin@localhost"},
    "sk": {"S": "PROFILE"},
    "email": {"S": "admin@localhost"},
    "displayName": {"S": "Local Admin"},
    "defaultRole": {"S": "admin"},
    "passwordHash": {"S": "'"$ADMIN_PASSWORD_HASH"'"},
    "gsi1pk": {"S": "ROLE#admin"},
    "gsi1sk": {"S": "USER#admin@localhost"},
    "disabled": {"BOOL": false},
    "localGroups": {"L": []},
    "createdAt": {"N": "'"$ADMIN_TIMESTAMP"'"},
    "createdBy": {"S": "setup-script"},
    "updatedAt": {"N": "'"$ADMIN_TIMESTAMP"'"}
}'

# =============================================
# Create AWS Infrastructure for demo-project (ECS)
# LocalStack Community limitations:
#   - No ELBv2/ALB support (Pro only)
#   - No RDS/ElastiCache (Pro only)
#   - ECS services created without load balancers
# =============================================
echo ""
echo "Creating AWS infrastructure for demo-project..."
echo ""

# Create VPC
echo "  - Creating VPC..."
VPC_ID=$(aws_cmd ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text)
aws_cmd ec2 create-tags --resources "$VPC_ID" --tags Key=Name,Value=demo-vpc Key=Project,Value=demo-project

# Create Subnets
echo "  - Creating subnets..."
SUBNET_PUBLIC_1=$(aws_cmd ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24 --availability-zone "${REGION}a" --query 'Subnet.SubnetId' --output text)
SUBNET_PUBLIC_2=$(aws_cmd ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.2.0/24 --availability-zone "${REGION}b" --query 'Subnet.SubnetId' --output text)
SUBNET_PRIVATE_1=$(aws_cmd ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.10.0/24 --availability-zone "${REGION}a" --query 'Subnet.SubnetId' --output text)
SUBNET_PRIVATE_2=$(aws_cmd ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.11.0/24 --availability-zone "${REGION}b" --query 'Subnet.SubnetId' --output text)

aws_cmd ec2 create-tags --resources "$SUBNET_PUBLIC_1" --tags Key=Name,Value=demo-public-1
aws_cmd ec2 create-tags --resources "$SUBNET_PUBLIC_2" --tags Key=Name,Value=demo-public-2
aws_cmd ec2 create-tags --resources "$SUBNET_PRIVATE_1" --tags Key=Name,Value=demo-private-1
aws_cmd ec2 create-tags --resources "$SUBNET_PRIVATE_2" --tags Key=Name,Value=demo-private-2

# Create Security Groups
echo "  - Creating security groups..."
SG_WEB=$(aws_cmd ec2 create-security-group --group-name demo-web-sg --description "Web Security Group" --vpc-id "$VPC_ID" --query 'GroupId' --output text)
SG_ECS=$(aws_cmd ec2 create-security-group --group-name demo-ecs-sg --description "ECS Tasks Security Group" --vpc-id "$VPC_ID" --query 'GroupId' --output text)

aws_cmd ec2 authorize-security-group-ingress --group-id "$SG_WEB" --protocol tcp --port 80 --cidr 0.0.0.0/0
aws_cmd ec2 authorize-security-group-ingress --group-id "$SG_WEB" --protocol tcp --port 443 --cidr 0.0.0.0/0
aws_cmd ec2 authorize-security-group-ingress --group-id "$SG_ECS" --protocol tcp --port 8080 --cidr 10.0.0.0/16
aws_cmd ec2 authorize-security-group-ingress --group-id "$SG_ECS" --protocol tcp --port 3000 --cidr 10.0.0.0/16

# Note: ALB/ELBv2 is LocalStack Pro only - skipping
echo "  - Skipping ALB (LocalStack Pro feature)"

# Create ECS Cluster
echo "  - Creating ECS cluster..."
aws_cmd ecs create-cluster --cluster-name demo-dev-cluster > /dev/null

# Register Task Definitions
echo "  - Registering task definitions..."

# API Task Definition
aws_cmd ecs register-task-definition \
    --family demo-dev-api \
    --network-mode awsvpc \
    --requires-compatibilities FARGATE \
    --cpu 256 --memory 512 \
    --container-definitions '[{
        "name": "api",
        "image": "demo/api:latest",
        "essential": true,
        "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
        "environment": [
            {"name": "ENV", "value": "dev"},
            {"name": "PORT", "value": "8080"}
        ]
    }]' > /dev/null

# Web Task Definition
aws_cmd ecs register-task-definition \
    --family demo-dev-web \
    --network-mode awsvpc \
    --requires-compatibilities FARGATE \
    --cpu 256 --memory 512 \
    --container-definitions '[{
        "name": "web",
        "image": "demo/web:latest",
        "essential": true,
        "portMappings": [{"containerPort": 3000, "protocol": "tcp"}],
        "environment": [
            {"name": "ENV", "value": "dev"},
            {"name": "API_URL", "value": "http://api:8080"}
        ]
    }]' > /dev/null

# Worker Task Definition
aws_cmd ecs register-task-definition \
    --family demo-dev-worker \
    --network-mode awsvpc \
    --requires-compatibilities FARGATE \
    --cpu 512 --memory 1024 \
    --container-definitions '[{
        "name": "worker",
        "image": "demo/worker:latest",
        "essential": true,
        "portMappings": [{"containerPort": 8081, "protocol": "tcp"}],
        "environment": [
            {"name": "ENV", "value": "dev"},
            {"name": "QUEUE_URL", "value": "http://localhost:4566/queue/demo-queue"}
        ]
    }]' > /dev/null

# Create ECS Services (without load balancers - LocalStack limitation)
echo "  - Creating ECS services..."

aws_cmd ecs create-service \
    --cluster demo-dev-cluster \
    --service-name demo-dev-api \
    --task-definition demo-dev-api \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_PRIVATE_1,$SUBNET_PRIVATE_2],securityGroups=[$SG_ECS],assignPublicIp=DISABLED}" > /dev/null

aws_cmd ecs create-service \
    --cluster demo-dev-cluster \
    --service-name demo-dev-web \
    --task-definition demo-dev-web \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_PRIVATE_1,$SUBNET_PRIVATE_2],securityGroups=[$SG_ECS],assignPublicIp=DISABLED}" > /dev/null

aws_cmd ecs create-service \
    --cluster demo-dev-cluster \
    --service-name demo-dev-worker \
    --task-definition demo-dev-worker \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_PRIVATE_1,$SUBNET_PRIVATE_2],securityGroups=[$SG_ECS],assignPublicIp=DISABLED}" > /dev/null

echo ""
echo "AWS Infrastructure created:"
echo "  VPC: $VPC_ID"
echo "  Subnets: $SUBNET_PUBLIC_1, $SUBNET_PUBLIC_2, $SUBNET_PRIVATE_1, $SUBNET_PRIVATE_2"
echo "  Security Groups: $SG_WEB, $SG_ECS"
echo "  ECS Cluster: demo-dev-cluster"
echo "  ECS Services: demo-dev-api, demo-dev-web, demo-dev-worker"
echo ""
echo "Note: ALB/RDS/ElastiCache skipped (LocalStack Pro features)"

echo ""
echo "=============================================="
echo "LocalStack setup complete!"
echo "=============================================="
echo ""
echo "Tables created:"
for t in tokens device-codes users groups permissions audit config cache; do
    echo "  - ${TABLE_PREFIX}-$t"
done
echo ""
echo "Next steps:"
echo "  1. Start the frontend dev server:"
echo "     cd packages/frontend && pnpm dev"
echo ""
echo "  2. The frontend will connect to LocalStack at:"
echo "     DynamoDB: $ENDPOINT_URL"
echo ""
echo "Note: SST deploy is NOT required for local development."
echo "      This script bypasses SST because LocalStack Community"
echo "      doesn't support ECR (required by SST v3)."
echo ""
