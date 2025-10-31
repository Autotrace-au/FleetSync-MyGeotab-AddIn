# FleetBridge Property Manager - MyGeotab Add-In

A MyGeotab Add-In that manages custom properties required for the FleetBridge automation system.

## About FleetBridge

FleetBridge creates and configures Exchange equipment mailboxes for vehicles and trailers, sourced from MyGeotab assets, using an Azure Automation runbook orchestrator. This allows staff to book cars and trailers directly in Outlook.

## What This Add-In Does

This Add-In automatically creates and manages the custom properties in MyGeotab that the FleetBridge orchestrator requires:

- **Is this a bookable resource** - Controls whether the equipment mailbox accepts bookings
- **Asset Stored Location** - Physical location where the asset is stored
- **Plant No** - Plant or facility identifier
- **Year Purchased** - Year the asset was purchased
- **Allow Recurring Booking** - Whether recurring bookings are allowed
- **Approvers** - Comma or semicolon separated email addresses for booking approvers

## Installation

### Quick Install (2 minutes)

1. Log in to MyGeotab as an administrator
2. Navigate to **Administration → System → System Settings → Add-Ins**
3. Click **New Add-In**
4. Paste this URL:
   ```
   https://cdn.jsdelivr.net/gh/Autotrace-au/FleetBridge-MyGeotab-AddIn@main/configuration.json
   ```
5. Click **Save**
6. Refresh your browser

The Add-In will appear under **Administration → FleetBridge Properties**

## Usage

1. Navigate to **Administration → FleetBridge Properties**
2. Click **Check Properties** to scan for existing custom properties
3. If any required properties are missing, click **Create Missing Properties**
4. The Add-In will create all missing properties automatically

## Features

- ✓ Automatic detection of existing custom properties
- ✓ One-click creation of missing properties
- ✓ Visual status indicators for each property
- ✓ No manual configuration required
- ✓ Deployed directly from GitHub via jsDelivr CDN

## Requirements

- MyGeotab account with administrator privileges
- Internet connection to access the Add-In from jsDelivr CDN

## Support

For issues or questions, contact: sam@garageofawesome.com.au

## Related Projects

- [AHC-AssetCreator](https://github.com/Autotrace-au/AHC-AssetCreator) - The main FleetBridge orchestrator repository

## Licence

Copyright © 2025 Autotrace. All rights reserved.
