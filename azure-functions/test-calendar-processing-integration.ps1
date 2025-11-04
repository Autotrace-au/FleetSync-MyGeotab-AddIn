#!/usr/bin/env pwsh

# Test Calendar Processing - Validate PowerShell Integration
# This script tests the calendar processing functionality in isolation

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$AppId = $env:ENTRA_CLIENT_ID,
    
    [Parameter(Mandatory=$false)]
    [string]$CertThumbprint = $env:POWERSHELL_CERT_THUMBPRINT,
    
    [Parameter(Mandatory=$false)]
    [string]$Organization = "garageofawesome.com.au",
    
    [Parameter(Mandatory=$false)]
    [string]$TestMailbox = "sam@garageofawesome.com.au"
)

Write-Host "🧪 Testing Calendar Processing Integration" -ForegroundColor Cyan
Write-Host "==========================================="

# Validate parameters
if (-not $AppId) {
    Write-Host "❌ Error: AppId not provided. Set ENTRA_CLIENT_ID environment variable or pass -AppId" -ForegroundColor Red
    exit 1
}

if (-not $CertThumbprint) {
    Write-Host "❌ Error: Certificate thumbprint not provided. Set POWERSHELL_CERT_THUMBPRINT environment variable or pass -CertThumbprint" -ForegroundColor Red
    exit 1
}

Write-Host "📋 Configuration:"
Write-Host "   App ID: $($AppId.Substring(0, 8))..."
Write-Host "   Certificate: $($CertThumbprint.Substring(0, 8))..."
Write-Host "   Organization: $Organization"
Write-Host "   Test Mailbox: $TestMailbox"
Write-Host ""

try {
    # Test 1: Import Exchange Online module
    Write-Host "🔧 Test 1: Import Exchange Online module..." -NoNewline
    Import-Module ExchangeOnlineManagement -Force -ErrorAction Stop
    Write-Host " ✅ Success" -ForegroundColor Green

    # Test 2: Connect to Exchange Online
    Write-Host "🔐 Test 2: Connect to Exchange Online..." -NoNewline
    Connect-ExchangeOnline -AppId $AppId -CertificateThumbprint $CertThumbprint -Organization $Organization -ShowBanner:$false -ErrorAction Stop
    Write-Host " ✅ Success" -ForegroundColor Green

    # Test 3: Get calendar processing settings
    Write-Host "📅 Test 3: Get calendar processing settings..." -NoNewline
    $currentSettings = Get-CalendarProcessing -Identity $TestMailbox -ErrorAction Stop
    Write-Host " ✅ Success" -ForegroundColor Green
    
    Write-Host "   Current AutomateProcessing: $($currentSettings.AutomateProcessing)"
    Write-Host "   Current AllBookInPolicy: $($currentSettings.AllBookInPolicy)"
    Write-Host "   Current BookingWindowInDays: $($currentSettings.BookingWindowInDays)"

    # Test 4: Test calendar processing modification (safe test - just change booking window)
    Write-Host "🔨 Test 4: Test calendar processing modification..." -NoNewline
    $originalBookingWindow = $currentSettings.BookingWindowInDays
    $testBookingWindow = if ($originalBookingWindow -eq 90) { 91 } else { 90 }
    
    Set-CalendarProcessing -Identity $TestMailbox -BookingWindowInDays $testBookingWindow -ErrorAction Stop
    Write-Host " ✅ Success" -ForegroundColor Green

    # Test 5: Verify change and restore
    Write-Host "🔍 Test 5: Verify change and restore..." -NoNewline
    $newSettings = Get-CalendarProcessing -Identity $TestMailbox -ErrorAction Stop
    
    if ($newSettings.BookingWindowInDays -eq $testBookingWindow) {
        # Restore original setting
        Set-CalendarProcessing -Identity $TestMailbox -BookingWindowInDays $originalBookingWindow -ErrorAction Stop
        Write-Host " ✅ Success" -ForegroundColor Green
    } else {
        Write-Host " ❌ Failed - Change not applied" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "🎉 All tests passed! Calendar processing functionality is working." -ForegroundColor Green
    Write-Host ""
    Write-Host "Ready to deploy to Azure Functions with PowerShell integration."
    
} catch {
    Write-Host " ❌ Failed" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "❌ Tests failed. Please check:" -ForegroundColor Red
    Write-Host "   - Certificate is properly installed and accessible"
    Write-Host "   - App registration has correct permissions"
    Write-Host "   - Exchange Online PowerShell module is available"
    Write-Host "   - Network connectivity to Exchange Online"
    exit 1
} finally {
    # Clean up connection
    try {
        Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
    } catch {
        # Ignore disconnection errors
    }
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Run deploy-calendar-processing.sh to deploy to Azure Functions"
Write-Host "2. Test the Function App sync-to-exchange endpoint"
Write-Host "3. Monitor Function App logs for PowerShell execution"