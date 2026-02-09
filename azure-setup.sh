#!/bin/bash
# Azure Setup Script for AgentOS Hackathon
# Run this script to provision all required Azure resources
# Requires: Azure CLI installed, logged in with `az login`

set -e  # Exit on error

# Configuration
RESOURCE_GROUP="agentOS-hackathon"
LOCATION="eastus"
OPENAI_NAME="agentOS-openai"
COSMOS_NAME="agentOS-cosmos"
INSIGHTS_NAME="agentOS-insights"
ACR_NAME="agentOSacr"
CONTAINERAPP_ENV="agentOS-env"

echo "========================================="
echo "AgentOS Hackathon - Azure Setup"
echo "========================================="
echo ""
echo "This script will create:"
echo "  - Resource Group: $RESOURCE_GROUP"
echo "  - Azure OpenAI: $OPENAI_NAME"
echo "  - Cosmos DB: $COSMOS_NAME (serverless)"
echo "  - Application Insights: $INSIGHTS_NAME"
echo "  - Container Registry: $ACR_NAME"
echo "  - Container Apps Environment: $CONTAINERAPP_ENV"
echo ""
echo "Location: $LOCATION"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Step 1: Creating Resource Group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

echo ""
echo "Step 2: Creating Azure OpenAI Service..."
az cognitiveservices account create \
  --name $OPENAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --kind OpenAI \
  --sku S0 \
  --location $LOCATION \
  --yes

echo ""
echo "Step 3: Deploying GPT-4 Model..."
az cognitiveservices account deployment create \
  --name $OPENAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --deployment-name gpt-4 \
  --model-name gpt-4 \
  --model-version "0613" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name Standard

echo ""
echo "Step 4: Creating Cosmos DB (Serverless)..."
az cosmosdb create \
  --name $COSMOS_NAME \
  --resource-group $RESOURCE_GROUP \
  --locations regionName=$LOCATION \
  --capabilities EnableServerless \
  --default-consistency-level Session

echo ""
echo "Step 5: Creating Application Insights..."
az monitor app-insights component create \
  --app $INSIGHTS_NAME \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP \
  --kind web

echo ""
echo "Step 6: Creating Container Registry..."
az acr create \
  --name $ACR_NAME \
  --resource-group $RESOURCE_GROUP \
  --sku Basic \
  --admin-enabled true

echo ""
echo "Step 7: Creating Container Apps Environment..."
az containerapp env create \
  --name $CONTAINERAPP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

echo ""
echo "========================================="
echo "✅ All resources created successfully!"
echo "========================================="
echo ""
echo "Retrieving endpoints and credentials..."
echo ""

# Get OpenAI endpoint
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name $OPENAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "properties.endpoint" \
  --output tsv)

# Get OpenAI key
OPENAI_KEY=$(az cognitiveservices account keys list \
  --name $OPENAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "key1" \
  --output tsv)

# Get Cosmos endpoint
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name $COSMOS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "documentEndpoint" \
  --output tsv)

# Get Cosmos key
COSMOS_KEY=$(az cosmosdb keys list \
  --name $COSMOS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryMasterKey" \
  --output tsv)

# Get Application Insights connection string
INSIGHTS_CONN=$(az monitor app-insights component show \
  --app $INSIGHTS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "connectionString" \
  --output tsv)

# Get ACR credentials
ACR_USERNAME=$(az acr credential show \
  --name $ACR_NAME \
  --query "username" \
  --output tsv)

ACR_PASSWORD=$(az acr credential show \
  --name $ACR_NAME \
  --query "passwords[0].value" \
  --output tsv)

# Create .env file
ENV_FILE="/home/agent/projects/ms-agent-framework-hackathon/.env"
cat > $ENV_FILE << EOF
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=$OPENAI_ENDPOINT
AZURE_OPENAI_KEY=$OPENAI_KEY
AZURE_OPENAI_DEPLOYMENT=gpt-4

# Cosmos DB
COSMOS_ENDPOINT=$COSMOS_ENDPOINT
COSMOS_KEY=$COSMOS_KEY

# Application Insights
APPLICATIONINSIGHTS_CONNECTION_STRING=$INSIGHTS_CONN

# Container Registry
ACR_NAME=$ACR_NAME
ACR_USERNAME=$ACR_USERNAME
ACR_PASSWORD=$ACR_PASSWORD

# Azure Settings
AZURE_RESOURCE_GROUP=$RESOURCE_GROUP
AZURE_LOCATION=$LOCATION
CONTAINERAPP_ENV=$CONTAINERAPP_ENV
EOF

echo ""
echo "========================================="
echo "Configuration saved to: $ENV_FILE"
echo "========================================="
echo ""
echo "Azure OpenAI Endpoint: $OPENAI_ENDPOINT"
echo "Cosmos DB Endpoint: $COSMOS_ENDPOINT"
echo "Container Registry: $ACR_NAME.azurecr.io"
echo ""
echo "Next steps:"
echo "  1. Review the .env file"
echo "  2. Test connection: python test_azure_connection.py"
echo "  3. Start development!"
echo ""
echo "Estimated monthly cost (light usage): ~$30-40"
echo "Your Azure free credit: $200 (should last the entire hackathon)"
echo ""
