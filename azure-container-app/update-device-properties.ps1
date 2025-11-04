#!/usr/bin/env pwsh
#Requires -Version 7

<#
.SYNOPSIS
    Updates MyGeotab device custom properties
.DESCRIPTION
    Updates custom properties for specified MyGeotab devices using the MyGeotab API
.PARAMETER ApiKey
    MyGeotab API key for authentication
.PARAMETER DeviceUpdates
    Array of device updates with deviceId and customProperties
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,
    
    [Parameter(Mandatory=$true)]
    [object[]]$DeviceUpdates
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Initialize response
$response = @{
    success = $false
    updated = 0
    failed = 0
    results = @()
    executionTimeMs = 0
}

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

try {
    Write-Host "Starting device property updates..."
    Write-Host "Updates to process: $($DeviceUpdates.Count)"
    
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
    
    # Process each device update
    foreach ($update in $DeviceUpdates) {
        $deviceId = $update.deviceId
        $properties = $update.customProperties
        
        Write-Host "`nProcessing device: $deviceId"
        
        $deviceResult = @{
            deviceId = $deviceId
            status = "pending"
        }
        
        try {
            # Build Python script to update device properties
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
    device = api.get('Device', id='$deviceId')[0]
    
    # Update custom properties
    properties = $($properties | ConvertTo-Json -Compress -Depth 10)
    
    # MyGeotab stores custom properties in customData field
    if not hasattr(device, 'customData') or device['customData'] is None:
        device['customData'] = {}
    
    # Update properties
    for key, value in properties.items():
        device['customData'][key] = value
    
    # Save device
    api.set('Device', device)
    
    print(json.dumps({
        'success': True,
        'deviceId': '$deviceId',
        'updatedProperties': properties
    }))
    
except Exception as e:
    print(json.dumps({
        'success': False,
        'deviceId': '$deviceId',
        'error': str(e)
    }), file=sys.stderr)
    sys.exit(1)
"@
            
            # Execute Python script
            $pythonOutput = $pythonScript | python3 -u - 2>&1
            $pythonExitCode = $LASTEXITCODE
            
            if ($pythonExitCode -eq 0) {
                $result = $pythonOutput | ConvertFrom-Json
                
                $deviceResult.status = "success"
                $deviceResult.updatedProperties = $result.updatedProperties
                
                Write-Host "✓ Successfully updated device: $deviceId"
                $response.updated++
            }
            else {
                throw "Python script failed: $pythonOutput"
            }
        }
        catch {
            $errorMessage = $_.Exception.Message
            Write-Host "✗ Failed to update device ${deviceId}: $errorMessage"
            
            $deviceResult.status = "failed"
            $deviceResult.error = $errorMessage
            $response.failed++
        }
        
        $response.results += $deviceResult
    }
    
    # Mark as successful if at least one device was updated
    $response.success = ($response.updated -gt 0)
    
}
catch {
    $errorMessage = $_.Exception.Message
    Write-Host "ERROR: $errorMessage"
    
    $response.success = $false
    $response.error = $errorMessage
}
finally {
    $stopwatch.Stop()
    $response.executionTimeMs = $stopwatch.Elapsed.TotalMilliseconds
    
    Write-Host "`nExecution Summary:"
    Write-Host "- Updated: $($response.updated)"
    Write-Host "- Failed: $($response.failed)"
    Write-Host "- Duration: $([math]::Round($response.executionTimeMs / 1000, 2))s"
}

# Return JSON response
$response | ConvertTo-Json -Depth 10 -Compress
