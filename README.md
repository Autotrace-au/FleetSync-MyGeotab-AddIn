# FleetBridge Property Manager - MyGeotab Add-In

FleetBridge is a multi-tenant SaaS MyGeotab Add-In that synchronises fleet assets with Microsoft Exchange Online equipment mailboxes and exposes booking policy management (recurring bookings, booking window, double-booking, approvers, managers, language).

## Repository Structure (Condensed)

```
mygeotab-addin/      # Frontend (HTML/JS/CSS)
azure-container-app/ # Container App (PowerShell + Python)
azure-functions/     # Legacy Function App (superseded)
docs/                # All documentation (see WIKI_INDEX.md)
scripts/             # Automation & setup scripts
```

## Documentation

All detailed guides have moved to `docs/`. Start here:

- **[Wiki Index](./docs/WIKI_INDEX.md)** – Categorised entry point
- **[Quick Start](./docs/QUICK_START.md)** – Minimal setup flow
- **[Deployment Guide](./docs/DEPLOYMENT.md)** – Full deployment
- **[Troubleshooting (Device Properties)](./docs/DEVICE_PROPERTY_UPDATE_TROUBLESHOOTING.md)** – Property update resolution

## Key Capabilities

- Equipment booking via Outlook / Teams (Exchange resource mailboxes)
- Centralised booking properties (8 custom properties created & managed)
- Group-based bulk updates for assets
- Multi-tenant isolation (API key & Key Vault secrets)
- Scalable PowerShell calendar processing (Container Apps)

## Getting Started (Summary)
1. Create / verify required Exchange permissions (see Modern RBAC guide).
2. Follow Quick Start to deploy container app + configure API key.
3. Use Add-In Property Setup tab to create missing custom properties.
4. Configure Sync endpoint and test.

## Security & Multi-Tenancy (Highlights)
- Per-tenant isolation (Key Vault segmented secrets)
- Equipment mailbox scope only
- Certificate & managed identity based access
- Audit via Application Insights traces

## Core UI Features (Add-In)
1. Property Setup – Detect/create required custom properties
2. Manage Assets – Group templates & bulk property application
3. Sync to Exchange – Configure & test backend endpoints

## Architecture Overview
High-level: Add-In (browser) → API (Container App PowerShell+Python) → Exchange Online & MyGeotab APIs. Legacy Azure Function retained for historical reference (see archive docs).

## Install (Quick)
Add-In manifest URL:
```
https://raw.githubusercontent.com/Autotrace-au/FleetBridge-MyGeotab-AddIn/main/mygeotab-addin/configuration.json
```

### For Administrators (Azure Function Setup)

See [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) for complete deployment instructions including:
- Azure resource provisioning
- Key Vault configuration
- Client onboarding process
- Multi-tenant setup

## Usage

### First-Time Setup

1. Navigate to **Administration → FleetBridge Properties**
2. Go to the **Property Setup** tab
3. Click **Check Properties** to scan for existing custom properties
4. If any required properties are missing, click **Create Missing Properties**
5. Go to the **Sync to Exchange** tab
6. Enter your Azure Function configuration (provided by your administrator)
7. Click **Save Configuration** and **Test Connection**

### Managing Assets

1. Go to the **Manage Assets** tab
2. **Create a group** with predefined booking policies:
   - Click **Create Group**
   - Enter group name and configure properties
   - Click **Save Group**
3. **Assign assets to groups**:
   - Select an asset from the table
   - Choose a group from the dropdown
   - Click **Assign to Group**
   - Properties are automatically updated in MyGeotab

### Property Updates
Group assignment applies all booking property values; existing values preserved unless overwritten.

## Features

### Property Management

- Automatic detection of existing custom properties
- One-click creation of missing properties
- Visual status indicators for each property
- No manual configuration required


### Asset Management

- Group-based property templates
- Bulk property updates
- Visual asset table with search and sort
- Group filtering (grouped vs ungrouped)
- Real-time property updates


### Multi-Tenant SaaS

- API key authentication per client
- Secure credential storage in Azure Key Vault
- Usage tracking for billing
- Isolated client data
- Scalable architecture


### Developer Experience

- No build process required
- Direct GitHub deployment
- Comprehensive logging
- CORS support for cross-origin requests
- Detailed error messages


## Requirements

### For End Users

- MyGeotab account with administrator privileges
- Internet connection to access the Add-In
- Azure Function configuration (provided by administrator)

### For Administrators

- Azure subscription
- Azure CLI installed
- Python 3.11+ for local development
- Azure Functions Core Tools v4

## Troubleshooting

### Properties Not Updating

1. Check Azure Function configuration in the **Sync to Exchange** tab
2. Click **Test Connection** to verify connectivity
3. Check browser console for error messages (F12)
4. Verify API key is correct

### Connection Errors

1. Verify Azure Function URL is correct (should end with `/api/update-device-properties`)
2. Verify Function Key is correct (no extra spaces)
3. Check CORS settings in Azure Function App
4. Check Application Insights logs for detailed errors

### Properties Toggling/Clearing

This issue was fixed in version 6.1.1+ by updating the full device object instead of just the custom properties. Make sure you're using the latest version.

### Advanced

See full troubleshooting: `docs/DEVICE_PROPERTY_UPDATE_TROUBLESHOOTING.md`.

## Monitoring Snippets

```kusto
traces | where timestamp > ago(1h) and message contains "USAGE:" | order by timestamp desc
```

```kusto
traces | where timestamp > ago(1h) and severityLevel >= 3 | order by timestamp desc
```

```kusto
traces | where timestamp > ago(1h) and (message contains "property" or message contains "Property")
```


## Security

- **API Keys**: Unique per client, stored in Azure Key Vault
- **Credentials**: Never stored in code or configuration files
- **Managed Identity**: Azure Function uses Managed Identity to access Key Vault
- **CORS**: Restricted to MyGeotab domains
- **HTTPS**: All communication encrypted with TLS 1.2+

## Support

- Email: [sam@garageofawesome.com.au](mailto:sam@garageofawesome.com.au)
- Issues: [GitHub Issue Tracker](https://github.com/Autotrace-au/FleetBridge-MyGeotab-AddIn/issues)

## Related Projects

- [autotrace-fields](https://github.com/Autotrace-au/autotrace-fields) - CSV bulk upload tool for MyGeotab custom properties
- [AHC-AssetCreator](https://github.com/Autotrace-au/AHC-AssetCreator) - Legacy FleetBridge orchestrator

## Changelog (Summary)

See `docs/IMPLEMENTATION_SUMMARY.md` & `docs/MIGRATION_GUIDE.md` for historical detail.

## Licence

Copyright © 2025 Autotrace. All rights reserved.

This software is proprietary and confidential. Unauthorised copying, distribution, or use is strictly prohibited.
