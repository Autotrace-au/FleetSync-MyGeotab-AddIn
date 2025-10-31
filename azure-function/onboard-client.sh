#!/bin/bash

# FleetSync Client Onboarding Script
# This script creates an API key for a new client and stores their credentials in Key Vault

set -e  # Exit on error

# Configuration - UPDATE THESE VALUES
KEY_VAULT="fleetsync-vault"

# Check arguments
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <client-name> <mygeotab-database> <mygeotab-username> <mygeotab-password>"
    echo ""
    echo "Example:"
    echo "  $0 \"Acme Corp\" \"acme\" \"admin@acme.com\" \"password123\""
    exit 1
fi

CLIENT_NAME=$1
DATABASE=$2
USERNAME=$3
PASSWORD=$4

echo "=========================================="
echo "FleetSync Client Onboarding"
echo "=========================================="
echo ""
echo "Client Name: $CLIENT_NAME"
echo "Database: $DATABASE"
echo "Username: $USERNAME"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Generate unique API key (UUID without dashes, lowercase)
API_KEY=$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-')

echo ""
echo "Generated API Key: $API_KEY"

# Store credentials in Key Vault
echo ""
echo "Storing credentials in Key Vault..."

az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "client-${API_KEY}-database" \
  --value "$DATABASE" \
  > /dev/null

az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "client-${API_KEY}-username" \
  --value "$USERNAME" \
  > /dev/null

az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "client-${API_KEY}-password" \
  --value "$PASSWORD" \
  > /dev/null

# Store client metadata (for reference)
CLIENT_METADATA=$(cat <<EOF
{
  "clientName": "$CLIENT_NAME",
  "database": "$DATABASE",
  "username": "$USERNAME",
  "onboardedDate": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
)

az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "client-${API_KEY}-metadata" \
  --value "$CLIENT_METADATA" \
  > /dev/null

echo "✓ Credentials stored successfully"

# Create client configuration file
CONFIG_FILE="client-configs/${CLIENT_NAME// /-}-config.json"
mkdir -p client-configs

cat > "$CONFIG_FILE" <<EOF
{
  "clientName": "$CLIENT_NAME",
  "apiKey": "$API_KEY",
  "database": "$DATABASE",
  "onboardedDate": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "addInConfiguration": {
    "name": "FleetSync Property Manager",
    "supportEmail": "support@yourcompany.com",
    "version": "6.0.0",
    "items": [
      {
        "url": "https://raw.githubusercontent.com/Autotrace-au/FleetSync-MyGeotab-AddIn/COMMIT_HASH/index.html?v=6.0",
        "path": "ActivityLink",
        "menuName": {
          "en": "FleetSync Property Manager"
        }
      }
    ]
  },
  "instructions": [
    "1. Update index.html with the API key below",
    "2. Commit and push to GitHub",
    "3. Update the commit hash in the configuration above",
    "4. Send the configuration JSON URL to the client",
    "5. Provide installation instructions"
  ]
}
EOF

echo ""
echo "=========================================="
echo "Client Onboarded Successfully!"
echo "=========================================="
echo ""
echo "Client Name: $CLIENT_NAME"
echo "API Key: $API_KEY"
echo "Database: $DATABASE"
echo ""
echo "Configuration file saved to:"
echo "  $CONFIG_FILE"
echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Update index.html with this API key:"
echo "   const CLIENT_API_KEY = '$API_KEY';"
echo ""
echo "2. Or create a client-specific version of the Add-In"
echo ""
echo "3. Test the API key:"
echo "   curl -X POST https://fleetsync-mygeotab.azurewebsites.net/api/update-device-properties?code=YOUR_FUNCTION_KEY \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"apiKey\": \"$API_KEY\", \"deviceId\": \"b1\", \"properties\": {\"bookable\": true}}'"
echo ""
echo "4. To revoke access, delete the secrets from Key Vault:"
echo "   az keyvault secret delete --vault-name $KEY_VAULT --name client-${API_KEY}-database"
echo "   az keyvault secret delete --vault-name $KEY_VAULT --name client-${API_KEY}-username"
echo "   az keyvault secret delete --vault-name $KEY_VAULT --name client-${API_KEY}-password"
echo "   az keyvault secret delete --vault-name $KEY_VAULT --name client-${API_KEY}-metadata"
echo ""

