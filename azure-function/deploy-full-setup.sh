#!/bin/bash

# FleetBridge Azure Function - Full Multi-Tenant Deployment Script
# This script deploys the complete multi-tenant architecture with Key Vault

set -e  # Exit on error

# Configuration - UPDATE THESE VALUES
RESOURCE_GROUP="FleetBridgeRG"
LOCATION="australiaeast"
STORAGE_ACCOUNT="fleetbridgestore"
FUNCTION_APP="fleetbridge-mygeotab"
KEY_VAULT="fleetbridge-vault"

echo "=========================================="
echo "FleetBridge Multi-Tenant Deployment"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  Storage Account: $STORAGE_ACCOUNT"
echo "  Function App: $FUNCTION_APP"
echo "  Key Vault: $KEY_VAULT"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Step 1: Login to Azure
echo ""
echo "Step 1: Logging in to Azure..."
az login

# Step 2: Create Resource Group
echo ""
echo "Step 2: Creating resource group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# Step 3: Create Storage Account
echo ""
echo "Step 3: Creating storage account..."
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Step 4: Create Key Vault
echo ""
echo "Step 4: Creating Key Vault..."
az keyvault create \
  --name $KEY_VAULT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Step 5: Create Function App
echo ""
echo "Step 5: Creating Function App..."
az functionapp create \
  --resource-group $RESOURCE_GROUP \
  --consumption-plan-location $LOCATION \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name $FUNCTION_APP \
  --storage-account $STORAGE_ACCOUNT \
  --os-type Linux

# Step 6: Enable Managed Identity
echo ""
echo "Step 6: Enabling managed identity for Function App..."
az functionapp identity assign \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP

# Get the principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP \
  --query principalId \
  --output tsv)

echo "  Principal ID: $PRINCIPAL_ID"

# Step 7: Grant Function App access to Key Vault
echo ""
echo "Step 7: Granting Function App access to Key Vault..."
az keyvault set-policy \
  --name $KEY_VAULT \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list

# Step 8: Configure Function App settings
echo ""
echo "Step 8: Configuring Function App settings..."
az functionapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP \
  --settings \
    "KEY_VAULT_URL=https://${KEY_VAULT}.vault.azure.net/" \
    "USE_KEY_VAULT=true"

# Step 9: Configure CORS
echo ""
echo "Step 9: Configuring CORS..."
az functionapp cors add \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP \
  --allowed-origins "https://*.geotab.com" "https://*.geotab.com.au"

# Step 10: Deploy Function
echo ""
echo "Step 10: Deploying function code..."
func azure functionapp publish $FUNCTION_APP

# Step 11: Get Function Key
echo ""
echo "Step 11: Getting function key..."
FUNCTION_KEY=$(az functionapp keys list \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP \
  --query "functionKeys.default" \
  --output tsv)

# Step 12: Display summary
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Function URL:"
echo "  https://${FUNCTION_APP}.azurewebsites.net/api/update-device-properties"
echo ""
echo "Function Key:"
echo "  $FUNCTION_KEY"
echo ""
echo "Key Vault URL:"
echo "  https://${KEY_VAULT}.vault.azure.net/"
echo ""
echo "Health Check URL:"
echo "  https://${FUNCTION_APP}.azurewebsites.net/api/health"
echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Test the health endpoint:"
echo "   curl https://${FUNCTION_APP}.azurewebsites.net/api/health"
echo ""
echo "2. Update index.html with these values:"
echo "   AZURE_FUNCTION_URL = 'https://${FUNCTION_APP}.azurewebsites.net/api/update-device-properties'"
echo "   AZURE_FUNCTION_KEY = '$FUNCTION_KEY'"
echo ""
echo "3. To onboard a new client, run:"
echo "   ./onboard-client.sh <client-name> <database> <username> <password>"
echo ""
echo "4. View logs:"
echo "   az functionapp log tail --resource-group $RESOURCE_GROUP --name $FUNCTION_APP"
echo ""

