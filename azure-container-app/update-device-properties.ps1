#!/usr/bin/env pwsh
#Requires -Version 7

<#
.SYNOPSIS
    Updates MyGeotab device custom properties
.DESCRIPTION
    Updates custom properties for specified MyGeotab devices using the MyGeotab API
    Matches the logic from the proven Azure Function implementation
.PARAMETER ApiKey
    MyGeotab API key for authentication
.PARAMETER DeviceId
    Device ID to update
.PARAMETER Properties
    Properties object to update
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,
    
    [Parameter(Mandatory=$true)]
    [string]$DeviceId,
    
    [Parameter(Mandatory=$true)]
    [object]$Properties
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Initialize response
$response = @{
    success = $false
    message = ""
    database = ""
    deviceId = $DeviceId
    executionTimeMs = 0
}

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

try {
    Write-Host "Starting device property update for device: $DeviceId"
    
    # Login to Azure using managed identity (for Container App)
    try {
        $null = az login --identity 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Logged in to Azure using managed identity"
        }
    }
    catch {
        Write-Host "Note: Azure login with managed identity failed, continuing..."
    }
    
    # Get MyGeotab credentials from Key Vault
    Write-Host "Retrieving MyGeotab credentials from Key Vault..."
    $secretPrefix = "client-$ApiKey"
    
    $mygeotabUsername = az keyvault secret show --vault-name fleetbridge-vault --name "$secretPrefix-username" --query value -o tsv 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to retrieve MyGeotab username: $mygeotabUsername"
    }
    
    $mygeotabPassword = az keyvault secret show --vault-name fleetbridge-vault --name "$secretPrefix-password" --query value -o tsv 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to retrieve MyGeotab password: $mygeotabPassword"
    }
    
    $mygeotabDatabase = az keyvault secret show --vault-name fleetbridge-vault --name "$secretPrefix-database" --query value -o tsv 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to retrieve MyGeotab database: $mygeotabDatabase"
    }
    
    Write-Host "Retrieved credentials for database: $mygeotabDatabase"
    $response.database = $mygeotabDatabase
    
    # Build Python script to update device properties (matches Azure Function logic)
    $pythonScript = @"
import mygeotab
import sys
import json

try:
    # Authenticate
    api = mygeotab.API(
        username='$mygeotabUsername',
        password='$mygeotabPassword',
        database='$mygeotabDatabase'
    )
    api.authenticate()
    
    # Get device
    print(f'Fetching device: $DeviceId', file=sys.stderr)
    devices = api.get('Device', search={'id': '$DeviceId'})
    if not devices:
        print(json.dumps({
            'success': False,
            'error': 'Device not found: $DeviceId'
        }))
        sys.exit(1)
    
    device = devices[0]
    print(f'Device retrieved: {device.get("name")}', file=sys.stderr)
    
    # Fetch property definitions
    print('Fetching property definitions', file=sys.stderr)
    all_properties = api.get('Property')
    
    # Property name mapping (matches Azure Function)
    property_mapping = {
        'bookable': 'Enable Equipment Booking',
        'recurring': 'Allow Recurring Bookings',
        'approvers': 'Booking Approvers',
        'fleetManagers': 'Fleet Managers',
        'conflicts': 'Allow Double Booking',
        'windowDays': 'Booking Window (Days)',
        'maxDurationHours': 'Maximum Booking Duration (Hours)',
        'language': 'Mailbox Language'
    }
    
    # Build property lookup
    prop_lookup = {}
    for key, prop_name in property_mapping.items():
        matching_prop = next((p for p in all_properties if p.get('name') == prop_name), None)
        if matching_prop:
            prop_lookup[key] = {
                'id': matching_prop['id'],
                'setId': matching_prop.get('propertySet', {}).get('id'),
                'name': prop_name
            }
    
    print(f'Found {len(prop_lookup)} property definitions', file=sys.stderr)
    
    # Get properties to update from PowerShell
    properties = $($Properties | ConvertTo-Json -Compress -Depth 10)
    
    # Build updated customProperties array
    custom_properties = device.get('customProperties', [])
    
    for key, value in properties.items():
        if key not in prop_lookup:
            print(f'Property not found: {key}', file=sys.stderr)
            continue
        
        prop_info = prop_lookup[key]
        
        # Convert empty strings to None
        if value == '':
            value = None
        
        # Find existing PropertyValue
        existing_index = next(
            (i for i, pv in enumerate(custom_properties) 
             if pv.get('property', {}).get('id') == prop_info['id']),
            None
        )
        
        # Create PropertyValue structure
        property_value = {
            'property': {
                'id': prop_info['id'],
                'propertySet': {
                    'id': prop_info['setId']
                }
            },
            'value': value
        }
        
        if existing_index is not None:
            # Update existing
            print(f'Updating property: {key} = {value}', file=sys.stderr)
            custom_properties[existing_index] = property_value
        else:
            # Add new
            print(f'Adding property: {key} = {value}', file=sys.stderr)
            custom_properties.append(property_value)
    
    # Update device customProperties
    device['customProperties'] = custom_properties
    
    # Call Set to update the device
    print('Calling Set to update device', file=sys.stderr)
    api.set('Device', device)
    
    print('Device updated successfully', file=sys.stderr)
    
    print(json.dumps({
        'success': True,
        'message': f'Device {device.get("name")} updated successfully',
        'database': '$mygeotabDatabase',
        'deviceId': '$DeviceId'
    }))
    
except Exception as e:
    print(f'Error updating device: {str(e)}', file=sys.stderr)
    print(json.dumps({
        'success': False,
        'error': str(e)
    }))
    sys.exit(1)
"@
    
    # Execute Python script
    Write-Host "Executing Python script to update device..."
    $pythonOutput = $pythonScript | python3 -u - 2>&1
    $pythonExitCode = $LASTEXITCODE
    
    if ($pythonExitCode -eq 0) {
        # Parse the last line as JSON (the actual result)
        $outputLines = $pythonOutput -split "`n"
        $jsonLine = $outputLines[-1]
        $result = $jsonLine | ConvertFrom-Json
        
        $response.success = $result.success
        $response.message = $result.message
        $response.database = $result.database
        
        Write-Host "✓ Successfully updated device: $DeviceId"
    }
    else {
        # Try to parse error from output
        $outputLines = $pythonOutput -split "`n"
        $jsonLine = $outputLines[-1]
        try {
            $errorResult = $jsonLine | ConvertFrom-Json
            throw $errorResult.error
        }
        catch {
            throw "Python script failed: $pythonOutput"
        }
    }
    
}
catch {
    $errorMessage = $_.Exception.Message
    Write-Host "ERROR: $errorMessage"
    
    $response.success = $false
    $response.message = "Error: $errorMessage"
}
finally {
    $stopwatch.Stop()
    $response.executionTimeMs = $stopwatch.Elapsed.TotalMilliseconds
    
    Write-Host "`nExecution Summary:"
    Write-Host "- Success: $($response.success)"
    Write-Host "- Duration: $([math]::Round($response.executionTimeMs / 1000, 2))s"
}

# Return JSON response
$response | ConvertTo-Json -Depth 10 -Compress
