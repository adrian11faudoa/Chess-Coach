#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy ChessCoach to AWS ECS
# Usage: ./scripts/deploy.sh [--region us-east-1] [--stack chesscoach] [--tag latest]
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-chesscoach}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --region) AWS_REGION="$2"; shift 2 ;;
    --stack)  STACK_NAME="$2"; shift 2 ;;
    --tag)    IMAGE_TAG="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "==> ChessCoach AWS Deployment"
echo "    Region: $AWS_REGION | Stack: $STACK_NAME | Tag: $IMAGE_TAG"

# ── 1. Get / create ECR repo ──────────────────────────────────────────────────
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/chesscoach"

echo ""
echo "==> 1/4  Authenticating to ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REPO" 2>/dev/null || true

# Ensure repo exists
aws ecr describe-repositories --repository-names chesscoach --region "$AWS_REGION" \
  &>/dev/null || \
aws ecr create-repository --repository-name chesscoach --region "$AWS_REGION" \
  --image-scanning-configuration scanOnPush=true >/dev/null

# ── 2. Build & push image ─────────────────────────────────────────────────────
echo ""
echo "==> 2/4  Building Docker image..."
cd "$PROJECT_DIR"
docker build -t chesscoach:$IMAGE_TAG .
docker tag chesscoach:$IMAGE_TAG "$ECR_REPO:$IMAGE_TAG"

echo "==> Pushing image to ECR..."
docker push "$ECR_REPO:$IMAGE_TAG"
echo "    Pushed: $ECR_REPO:$IMAGE_TAG"

# ── 3. Deploy / update CloudFormation ─────────────────────────────────────────
echo ""
echo "==> 3/4  Deploying CloudFormation stack '$STACK_NAME'..."

# Check if stack exists
STACK_EXISTS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [[ "$STACK_EXISTS" == "DOES_NOT_EXIST" ]]; then
  echo "    Stack not found. Please create it first with:"
  echo ""
  echo "    aws cloudformation deploy \\"
  echo "      --template-file infra/cloudformation.yml \\"
  echo "      --stack-name $STACK_NAME \\"
  echo "      --region $AWS_REGION \\"
  echo "      --capabilities CAPABILITY_NAMED_IAM \\"
  echo "      --parameter-overrides \\"
  echo "        VpcId=vpc-XXXXXXXX \\"
  echo "        SubnetIds=subnet-XXXXXXXX,subnet-YYYYYYYY \\"
  echo "        ContainerImage=$ECR_REPO:$IMAGE_TAG"
  echo ""
  echo "    After the stack is created, re-run this script to update."
  exit 0
fi

# Update task definition with new image
CLUSTER=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ECSCluster'].OutputValue" \
  --output text)

SERVICE=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ECSService'].OutputValue" \
  --output text)

echo "    Cluster: $CLUSTER / Service: $SERVICE"

# Force new deployment (pulls latest image with same tag)
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION" \
  --query "service.serviceName" \
  --output text

# ── 4. Wait for deployment ────────────────────────────────────────────────────
echo ""
echo "==> 4/4  Waiting for deployment to stabilise (up to 5 min)..."
aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --region "$AWS_REGION"

# Print URL
APP_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='AppURL'].OutputValue" \
  --output text)

echo ""
echo "✅  Deployment complete!"
echo "    URL: $APP_URL"
