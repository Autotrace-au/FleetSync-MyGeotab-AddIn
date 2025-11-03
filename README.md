# FleetBridge Property Manager - MyGeotab Add-In

A multi-tenant SaaS MyGeotab Add-In that manages equipment booking properties and synchronises assets with Microsoft Exchange Online equipment mailboxes. FleetBridge enables organisations to book vehicles and equipment directly through Outlook/Teams calendar.

## � Repository Structure

```
FleetBridge-MyGeotab-AddIn/
├── mygeotab-addin/              # MyGeotab Add-In frontend
│   ├── index.html               # Main Add-In interface
│   ├── styles.css              # Add-In styling
│   ├── configuration.json      # MyGeotab manifest
│   ├── images/                 # Icons and assets
│   └── translations/           # Language files
├── azure-functions/            # Backend Azure Functions
│   ├── function_app.py         # Main function application
│   ├── requirements.txt        # Python dependencies
│   ├── deploy-full-setup.sh    # Deployment script
│   └── onboard-client.sh       # Client onboarding
├── docs/                       # Documentation
│   ├── QUICK_START.md         # Getting started guide
│   ├── DEPLOYMENT.md          # Deployment instructions
│   └── *.md                   # Technical documentation
└── scripts/                   # Setup scripts
    ├── assign-impersonation-role.ps1
    └── *.ps1                  # PowerShell utilities
```

## � Quick Navigation

- **[MyGeotab Add-In](./mygeotab-addin/)** - Frontend interface for MyGeotab users
- **[Azure Functions](./azure-functions/)** - Backend SaaS service  
- **[Documentation](./docs/)** - Complete setup and usage guides
- **[Scripts](./scripts/)** - PowerShell utilities for Exchange setup

## �🚀 About FleetBridge

FleetBridge is a comprehensive multi-tenant SaaS solution that bridges MyGeotab fleet management with Microsoft Exchange Online equipment booking. It allows organisations to:

- **Book vehicles and equipment** directly in Outlook/Teams calendar
- **Manage booking policies** (approvals, recurring bookings, conflicts, booking windows)
- **Synchronise asset data** between MyGeotab and Exchange Online
- **Control access** with group-based permissions and booking approvers
- **Track usage** with Application Insights telemetry

## 📋 What This Add-In Does

This Add-In provides a complete property management interface with three main tabs:

### 1. Property Setup Tab
Automatically creates and manages 8 custom properties in MyGeotab:

- **Enable Equipment Booking** - Controls whether the equipment mailbox accepts bookings
- **Allow Recurring Bookings** - Whether recurring bookings are allowed
- **Booking Approvers** - Email addresses for booking approvers (comma/semicolon separated)
- **Fleet Managers** - Email addresses for fleet managers (comma/semicolon separated)
- **Allow Double Booking** - Whether the asset can be double-booked
- **Booking Window (Days)** - How far in advance bookings can be made
- **Maximum Booking Duration (Hours)** - Maximum duration for a single booking
- **Mailbox Language** - Language code for the equipment mailbox (e.g., en-AU, en-US)

### 2. Manage Assets Tab
Visual interface for managing assets and groups:

- **Create booking groups** with predefined property templates
- **Assign assets to groups** with one-click property updates
- **View all assets** in a searchable, sortable table
- **Filter by group** to see grouped vs ungrouped assets
- **Bulk property updates** by assigning multiple assets to the same group

### 3. Sync to Exchange Tab
Configuration for Azure Function integration:

- **Azure Function URL** - Endpoint for the multi-tenant Azure Function
- **Function Key** - Authentication key for the Azure Function
- **Client API Key** - Unique API key for multi-tenant authentication
- **Test connection** to verify configuration

## 🏗️ Architecture

FleetBridge uses a hybrid architecture:

### Frontend (MyGeotab Add-In)
- **Technology**: Pure HTML/CSS/JavaScript (no build process)
- **Hosting**: GitHub raw URLs (no CDN caching issues)
- **Version**: 6.1.1
- **Repository**: [FleetBridge-MyGeotab-AddIn](https://github.com/Autotrace-au/FleetBridge-MyGeotab-AddIn)

### Backend (Azure Function)
- **Technology**: Python 3.11 with MyGeotab Python SDK
- **Hosting**: Azure Functions (Consumption Plan)
- **Authentication**: Multi-tenant with API keys stored in Azure Key Vault
- **Monitoring**: Application Insights for usage tracking and billing
- **Endpoint**: `https://fleetbridge-mygeotab.azurewebsites.net/api/update-device-properties`

### Why Python Azure Function?

The MyGeotab JavaScript SDK has a persistent bug where updating device custom properties results in `JsonSerializerException` We switched to a Python Azure Function using the MyGeotab Python SDK, which works reliably.

## 📦 Installation

### For End Users (Quick Install - 2 minutes)

1. Log in to MyGeotab as an administrator
2. Navigate to **Administration → System → System Settings → Add-Ins**
3. Click **New Add-In**
4. Paste this URL:
   ```
   https://raw.githubusercontent.com/Autotrace-au/FleetBridge-MyGeotab-AddIn/main/mygeotab-addin/configuration.json
   ```
5. Click **Save**
6. Refresh your browser (Ctrl+Shift+R or Cmd+Shift+R)

The Add-In will appear under **Administration → FleetBridge Properties**

### For Administrators (Azure Function Setup)

See [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) for complete deployment instructions including:
- Azure resource provisioning
- Key Vault configuration
- Client onboarding process
- Multi-tenant setup

## 🎯 Usage

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

When you assign an asset to a group:
- All 8 booking properties are updated in MyGeotab
- Existing properties are preserved (no data loss)
- Changes are logged to Application Insights
- Updates are visible immediately in MyGeotab

## ✨ Features

### Property Management
- ✅ Automatic detection of existing custom properties
- ✅ One-click creation of missing properties
- ✅ Visual status indicators for each property
- ✅ No manual configuration required

### Asset Management
- ✅ Group-based property templates
- ✅ Bulk property updates
- ✅ Visual asset table with search and sort
- ✅ Group filtering (grouped vs ungrouped)
- ✅ Real-time property updates

### Multi-Tenant SaaS
- ✅ API key authentication per client
- ✅ Secure credential storage in Azure Key Vault
- ✅ Usage tracking for billing
- ✅ Isolated client data
- ✅ Scalable architecture

### Developer Experience
- ✅ No build process required
- ✅ Direct GitHub deployment
- ✅ Comprehensive logging
- ✅ CORS support for cross-origin requests
- ✅ Detailed error messages

## 🔧 Requirements

### For End Users
- MyGeotab account with administrator privileges
- Internet connection to access the Add-In
- Azure Function configuration (provided by administrator)

### For Administrators
- Azure subscription
- Azure CLI installed
- Python 3.11+ for local development
- Azure Functions Core Tools v4

## 🐛 Troubleshooting

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

## 📊 Monitoring

### Application Insights Queries

**View recent usage:**
```kusto
traces
| where timestamp > ago(1h)
| where message contains "USAGE:"
| order by timestamp desc
```

**View errors:**
```kusto
traces
| where timestamp > ago(1h)
| where severityLevel >= 3
| order by timestamp desc
```

**View property updates:**
```kusto
traces
| where timestamp > ago(1h)
| where message contains "property" or message contains "Property"
| order by timestamp desc
```

## 🔐 Security

- **API Keys**: Unique per client, stored in Azure Key Vault
- **Credentials**: Never stored in code or configuration files
- **Managed Identity**: Azure Function uses Managed Identity to access Key Vault
- **CORS**: Restricted to MyGeotab domains
- **HTTPS**: All communication encrypted with TLS 1.2+

## 📞 Support

For issues or questions:
- **Email**: sam@garageofawesome.com.au
- **GitHub Issues**: [Create an issue](https://github.com/Autotrace-au/FleetBridge-MyGeotab-AddIn/issues)

## 🔗 Related Projects

- [autotrace-fields](https://github.com/Autotrace-au/autotrace-fields) - CSV bulk upload tool for MyGeotab custom properties
- [AHC-AssetCreator](https://github.com/Autotrace-au/AHC-AssetCreator) - Legacy FleetBridge orchestrator

## 📝 Changelog

### Version 6.1.1 (2025-10-31)
- **Fixed**: Properties toggling between set and empty on repeated updates
- **Changed**: Now updates full device object instead of partial update
- **Improved**: Follows pattern from autotrace-fields repository

### Version 6.1 (2025-10-30)
- **Added**: User-configurable Azure Function settings
- **Added**: Configuration UI in Sync to Exchange tab
- **Added**: Connection testing
- **Fixed**: CORS issues with Azure Function

### Version 6.0 (2025-10-29)
- **Changed**: Switched from JavaScript SDK to Python Azure Function
- **Added**: Multi-tenant SaaS architecture
- **Added**: API key authentication
- **Added**: Azure Key Vault integration
- **Added**: Application Insights monitoring

### Version 5.x (2025-10-28)
- Multiple failed attempts to fix JavaScript SDK JsonSerializerException
- Attempted 11+ different approaches with JavaScript SDK

### Version 4.x and earlier
- Initial development
- Property setup functionality
- Asset management interface
- Group management

## 📄 Licence

Copyright © 2025 Autotrace. All rights reserved.

This software is proprietary and confidential. Unauthorised copying, distribution, or use is strictly prohibited.
