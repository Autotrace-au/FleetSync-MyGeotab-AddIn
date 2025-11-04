# Function App Configuration Backup

## Important Settings to Migrate to Container App

### Key Vault and Authentication
- **KEY_VAULT_URL**: https://fleetbridge-vault.vault.azure.net/
- **ENTRA_CLIENT_ID**: 7eeb2358-00de-4da9-a6b7-8522b5353ade
- **ENTRA_CLIENT_SECRET_NAME**: EntraAppClientSecret

### Domain Configuration
- **EQUIPMENT_DOMAIN**: equipment.garageofawesome.com.au

### Storage (Keep for Container App)
- **Storage Account**: fleetbridgestore
- **Key Vault**: fleetbridge-vault
- **Application Insights**: Keep for monitoring

## Resources to Delete
- **Function App**: fleetbridge-mygeotab
- **App Service Plan**: AustraliaEastLinuxDynamicPlan
- **Application Insights Components**: fleetbridge-mygeotab (App Insights)
- **Smart Detection Rules**: Failure Anomalies rules

## Resources to Keep
- **Storage Account**: fleetbridgestore (needed for Container App)
- **Key Vault**: fleetbridge-vault (contains certificates and secrets)
- **Resource Group**: FleetBridgeRG (reuse for Container App)