# Azure Functions

This folder contains the Azure Functions backend that powers the FleetBridge SaaS service.

## Files

- **`function_app.py`** - Main Azure Function application with all endpoints
- **`host.json`** - Azure Functions runtime configuration
- **`requirements.txt`** - Python dependencies
- **`deploy-full-setup.sh`** - Script to deploy the complete Azure infrastructure
- **`onboard-client.sh`** - Script to onboard new clients to the SaaS service
- **`setup-properties.py`** - Helper script for configuring client properties

## Endpoints

The function app provides these endpoints:

### Authentication
- `GET /api/authlogin` - Initiate OAuth login flow
- `GET /api/authcallback` - Handle OAuth callback
- `GET /api/authstatus` - Check authentication status

### Device Management  
- `POST /api/update-device-properties` - Update device properties in MyGeotab
- `POST /api/sync-to-exchange` - Sync devices to Exchange equipment mailboxes

### Testing & Health
- `GET /api/health` - Health check endpoint
- `GET /api/test-oauth` - Test OAuth configuration
- `GET /api/test-app-token` - Test application-level token and mailbox access
- `GET /api/test1` - Basic connectivity test

## Architecture

- **Multi-tenant SaaS** - Supports multiple clients with isolated data
- **OAuth 2.0** - Uses Microsoft Graph API with certificate-based authentication
- **Azure Key Vault** - Stores client secrets and certificates securely
- **Exchange Online** - Creates and manages equipment mailboxes

## Deployment

1. Run `deploy-full-setup.sh` to create all Azure resources
2. Configure client secrets in Azure Key Vault
3. Set up Exchange Online permissions (see root documentation)
4. Test with `test-app-token` endpoint

## Security

- All endpoints require API key authentication
- Certificate-based authentication for Microsoft Graph API  
- Rate limiting (30 requests per 60 seconds)
- Isolated per-client data storage in Key Vault

## Quick Start

```bash
cd azure-functions
chmod +x deploy-full-setup.sh onboard-client.sh
./deploy-full-setup.sh
./onboard-client.sh "Your Company" "database" "username" "password"
```

## Features

✅ API key authentication per client
✅ Credentials stored in Azure Key Vault
✅ Usage tracking for billing
✅ Health check endpoint
✅ Automated deployment scripts
✅ Client onboarding automation

## Documentation

- **[MULTI_TENANT_ARCHITECTURE.md](../MULTI_TENANT_ARCHITECTURE.md)** - Complete architecture guide
- **[DEPLOYMENT.md](../DEPLOYMENT.md)** - Deployment instructions
- **deploy-full-setup.sh** - Automated deployment script
- **onboard-client.sh** - Client onboarding script

## Support

Check Application Insights logs for troubleshooting.
