# FleetBridge MyGeotab Azure Function - Multi-Tenant Edition

Full multi-tenant Azure Function with API key support and Azure Key Vault integration.

## Quick Start

```bash
cd azure-function
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
