# Calendar Processing Deployment Guide

This document provides step-by-step instructions for deploying and testing the calendar processing solution.

## Overview

The calendar processing solution bridges the gap between Microsoft Graph API (which has limited calendar processing capabilities) and Exchange PowerShell cmdlets (which provide full calendar configuration). 

**Key Components:**
- `exchange_powershell.py` - Python module that executes PowerShell within Azure Functions
- `function_app.py` - Main Function App with integrated PowerShell execution  
- `deploy-calendar-processing.sh` - Deployment script with certificate setup
- `test-calendar-processing-integration.ps1` - Validation script

## Prerequisites

### Local Development
1. **PowerShell Core (pwsh)** installed
2. **Exchange Online PowerShell module** installed
3. **Azure CLI** installed and logged in
4. **Azure Functions Core Tools** installed

### Azure Resources
1. **Azure Function App** already deployed (`fleetbridge-mygeotab`)
2. **Key Vault** with managed identity access (`fleetbridge-vault`)
3. **Entra ID App Registration** with certificate authentication

## Step 1: Pre-Deployment Testing

Before deploying to Azure, test PowerShell functionality locally:

```bash
cd azure-functions
pwsh ./test-calendar-processing-integration.ps1
```

This will test:
- Exchange Online PowerShell module loading
- Certificate-based authentication
- Calendar processing cmdlets
- Settings modification and restoration

**Expected Output:**
```
🧪 Testing Calendar Processing Integration
===========================================
🔧 Test 1: Import Exchange Online module... ✅ Success
🔐 Test 2: Connect to Exchange Online... ✅ Success
📅 Test 3: Get calendar processing settings... ✅ Success
🔨 Test 4: Test calendar processing modification... ✅ Success
🔍 Test 5: Verify change and restore... ✅ Success

🎉 All tests passed! Calendar processing functionality is working.
```

## Step 2: Deploy to Azure Functions

Run the deployment script:

```bash
cd azure-functions
./deploy-calendar-processing.sh
```

This script will:
1. ✅ Verify Azure CLI authentication
2. ✅ Check Function App exists
3. ✅ Enable managed identity
4. ✅ Grant Key Vault access
5. ✅ Create PowerShell authentication certificate
6. ✅ Store certificate thumbprint in Key Vault
7. ✅ Deploy Function App code
8. ✅ Set environment variables
9. ✅ Test PowerShell Core availability

**Expected Output:**
```
🚀 Deploying Calendar Processing Solution for FleetSync
==================================================
✅ Logged in to subscription: xxxxx
✅ Function App found
✅ Function App Principal ID: xxxxx
✅ Key Vault access granted
✅ Certificate thumbprint: ABCD1234...
✅ PowerShell configuration stored
✅ Dependencies up to date
✅ Function App deployed
✅ Environment variables set
✅ PowerShell Core is available

🎉 Deployment Complete!
```

## Step 3: Test Function App Integration

Test the calendar processing via the Function App:

```bash
# Replace YOUR_API_KEY with actual client API key
curl -X POST https://fleetbridge-mygeotab.azurewebsites.net/api/sync-to-exchange \
  -H 'Content-Type: application/json' \
  -d '{"apiKey": "YOUR_API_KEY", "maxDevices": 1}'
```

**Expected Response:**
```json
{
  "success": true,
  "processed": 1,
  "successful": 1,
  "failed": 0,
  "results": [
    {
      "device": "Test Equipment",
      "serialNumber": "ABC123",
      "success": true,
      "email": "abc123@garageofawesome.com.au",
      "displayName": "Test Equipment"
    }
  ]
}
```

## Step 4: Monitor Execution

Monitor Function App logs to verify PowerShell execution:

```bash
az functionapp logs tail --name fleetbridge-mygeotab --resource-group fleetbridge-rg
```

**Look for these log entries:**
```
INFO: PowerShell credentials prepared: AppId=12345678..., Thumbprint=ABCD1234...
INFO: Updating calendar processing settings for abc123@garageofawesome.com.au
INFO: ✓ Successfully updated calendar processing for abc123@garageofawesome.com.au
```

## Troubleshooting

### PowerShell Module Issues
If PowerShell module import fails:

```bash
# Install/update Exchange Online module
pwsh -c "Install-Module ExchangeOnlineManagement -Force -AllowClobber"
```

### Certificate Authentication Issues
If certificate authentication fails:

1. **Check certificate in Key Vault:**
   ```bash
   az keyvault certificate show --vault-name fleetbridge-vault --name FleetSync-PowerShell
   ```

2. **Verify certificate thumbprint:**
   ```bash
   az keyvault secret show --vault-name fleetbridge-vault --name powershell-cert-thumbprint
   ```

3. **Check app registration permissions:**
   - Navigate to Azure Portal > App Registrations
   - Find your app registration
   - Verify Exchange Online permissions are granted

### PowerShell Core Availability
If `pwsh` is not available in Azure Functions:

- Azure Functions Linux runtime includes PowerShell Core by default
- Windows runtime may need custom configuration
- Consider using Linux consumption plan

### Exchange Online Connectivity
If Exchange Online connection fails:

1. **Test network connectivity:**
   ```bash
   curl -I https://outlook.office365.com
   ```

2. **Verify app registration:**
   - Check that certificate is uploaded to app registration
   - Verify Exchange Online API permissions
   - Ensure admin consent is granted

### Function App Memory Issues
If Function App runs out of memory during PowerShell execution:

1. **Increase Function App plan:**
   ```bash
   az functionapp plan update --name your-plan --resource-group fleetbridge-rg --sku P1V2
   ```

2. **Optimize PowerShell execution:**
   - Use shorter timeouts
   - Process devices in smaller batches
   - Implement retry logic

## Validation Checklist

After deployment, verify these capabilities:

- [ ] Function App responds to sync-to-exchange requests
- [ ] PowerShell modules load successfully
- [ ] Certificate authentication works
- [ ] Exchange Online connection established
- [ ] Calendar processing settings can be read
- [ ] Calendar processing settings can be modified
- [ ] Equipment mailbox booking policies applied
- [ ] Function App logs show successful PowerShell execution

## Next Steps

Once calendar processing is working:

1. **Test Equipment Mailbox Creation:**
   - Create actual resource mailboxes in Exchange Admin Center
   - Test full booking workflow from MyGeotab devices

2. **Production Integration:**
   - Remove maxDevices limit
   - Process all fleet devices
   - Monitor performance and reliability

3. **Modern RBAC Migration:**
   - Monitor for Exchange RBAC cmdlet availability
   - Plan migration from certificate authentication to modern RBAC

## Security Considerations

1. **Certificate Management:**
   - Certificates are stored securely in Key Vault
   - Automatic rotation may be needed for long-term deployment
   - Monitor certificate expiration

2. **Access Control:**
   - Function App uses managed identity for Key Vault access
   - PowerShell execution limited to calendar processing cmdlets
   - API keys required for Function App access

3. **Logging:**
   - PowerShell execution is logged but output is sanitized
   - No sensitive data (passwords, tokens) in logs
   - Audit trail for all equipment mailbox modifications