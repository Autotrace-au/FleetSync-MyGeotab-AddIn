# Equipment Mailbox Calendar Processing Module
# This module handles the calendar processing settings that are not available via Graph API
# Uses PowerShell Core to execute Exchange Online cmdlets

import subprocess
import json
import logging
import tempfile
import os
import asyncio
from typing import Dict, Any, Optional

class ExchangePowerShellExecutor:
    """
    Executes Exchange Online PowerShell cmdlets for calendar processing settings.
    This is necessary because Graph API doesn't support Set-CalendarProcessing functionality.
    """
    
    def __init__(self, app_id: str, cert_thumbprint: str, organization: str):
        self.app_id = app_id
        self.cert_thumbprint = cert_thumbprint
        self.organization = organization
    
    async def set_calendar_processing_async(self, mailbox_identity: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async wrapper for calendar processing configuration.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set_calendar_processing, mailbox_identity, settings)
    
    def set_calendar_processing(self, mailbox_identity: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Configure calendar processing settings for an equipment mailbox.
        
        Args:
            mailbox_identity: Email address or identity of the mailbox
            settings: Dictionary of calendar processing settings
        
        Returns:
            Dictionary with success status and any error messages
        """
        try:
            # Build the PowerShell script
            ps_script = self._build_calendar_processing_script(mailbox_identity, settings)
            
            # Execute PowerShell
            result = self._execute_powershell(ps_script)
            
            if result['returncode'] == 0 and "SUCCESS:" in result.get('output', ''):
                logging.info(f"Successfully updated calendar processing for {mailbox_identity}")
                return {'success': True, 'output': result.get('output', '')}
            else:
                error_msg = result.get('error', '') or result.get('output', 'Unknown error')
                logging.error(f"Failed to update calendar processing for {mailbox_identity}: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logging.error(f"Error setting calendar processing for {mailbox_identity}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _build_calendar_processing_script(self, mailbox_identity: str, settings: Dict[str, Any]) -> str:
        """
        Build PowerShell script for calendar processing configuration.
        """
        # Start with connection and error handling
        script_lines = [
            "try {",
            "    Import-Module ExchangeOnlineManagement -Force",
            "    ",
            "    # Connect using certificate authentication",
            "    # Note: On Linux/Azure Functions, we need to handle certificate differently",
            "    if ($IsWindows) {",
            f"        Connect-ExchangeOnline -AppId '{self.app_id}' -CertificateThumbprint '{self.cert_thumbprint}' -Organization '{self.organization}' -ShowBanner:$false",
            "    } else {",
            "        # For Linux/macOS, we would need to use certificate file path",
            "        # This is a fallback that may need certificate file setup",
            f"        Write-Warning 'Certificate thumbprint authentication not supported on this platform. AppId: {self.app_id[:8]}...'",
            "        throw 'Certificate authentication not available on non-Windows platforms'",
            "    }",
            "",
            "    # Configure calendar processing settings"
        ]
        
        # Build parameters based on settings
        params = []
        
        # Core booking settings
        if 'bookable' in settings:
            if settings['bookable']:
                params.extend([
                    "-AutomateProcessing AutoAccept",
                    "-AllBookInPolicy:$true",
                    "-AllRequestInPolicy:$false"
                ])
            else:
                params.extend([
                    "-AutomateProcessing None",
                    "-AllBookInPolicy:$false",
                    "-AllRequestInPolicy:$false",
                    "-BookingWindowInDays 0"
                ])
        
        # Delegates and approval
        if 'resourceDelegates' in settings and settings['resourceDelegates']:
            delegates_str = "'" + "','".join(settings['resourceDelegates']) + "'"
            params.extend([
                f"-ResourceDelegates @({delegates_str})",
                "-AllRequestInPolicy:$true",
                "-AllBookInPolicy:$false"
            ])
        
        # Other settings
        if 'allowConflicts' in settings:
            params.append(f"-AllowConflicts:${str(settings['allowConflicts']).lower()}")
        
        if 'bookingWindowInDays' in settings:
            params.append(f"-BookingWindowInDays {settings['bookingWindowInDays']}")
        
        if 'maximumDurationInMinutes' in settings:
            params.append(f"-MaximumDurationInMinutes {settings['maximumDurationInMinutes']}")
        
        if 'allowRecurringMeetings' in settings:
            params.append(f"-AllowRecurringMeetings:${str(settings['allowRecurringMeetings']).lower()}")
        
        if 'scheduleOnlyDuringWorkHours' in settings:
            params.append(f"-ScheduleOnlyDuringWorkHours:${str(settings['scheduleOnlyDuringWorkHours']).lower()}")
        
        # Additional response message
        if 'additionalResponse' in settings:
            response = settings['additionalResponse'].replace("'", "''")  # Escape single quotes
            params.extend([
                "-AddAdditionalResponse:$true",
                f"-AdditionalResponse '{response}'"
            ])
        
        # Build the command
        params_str = ' `\n        '.join(params)
        script_lines.extend([
            f"    Set-CalendarProcessing -Identity '{mailbox_identity}' `",
            f"        {params_str} `",
            "        -ErrorAction Stop",
            "",
            f"    Write-Output 'SUCCESS: Calendar processing updated for {mailbox_identity}'",
            "",
            "} catch {",
            "    Write-Output \"ERROR: $($_.Exception.Message)\"",
            "} finally {",
            "    try { Disconnect-ExchangeOnline -Confirm:$false } catch { }",
            "}"
        ])
        
        return '\n'.join(script_lines)
    
    def _execute_powershell(self, script: str) -> Dict[str, Any]:
        """
        Execute a PowerShell script and return the results.
        """
        try:
            # Create a temporary file for the script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False) as f:
                f.write(script)
                script_path = f.name
            
            try:
                # Execute PowerShell Core (pwsh must be available in Azure Functions)
                result = subprocess.run([
                    'pwsh', '-ExecutionPolicy', 'Bypass', '-File', script_path
                ], capture_output=True, text=True, timeout=120)  # 2 minute timeout
                
                return {
                    'output': result.stdout.strip(),
                    'error': result.stderr.strip(),
                    'returncode': result.returncode
                }
            finally:
                # Clean up temporary file
                try:
                    os.unlink(script_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return {'output': '', 'error': 'PowerShell execution timed out', 'returncode': -1}
        except Exception as e:
            return {'output': '', 'error': str(e), 'returncode': -1}


def create_equipment_mailbox_settings(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert device data into calendar processing settings.
    
    Args:
        device_data: MyGeotab device data with booking properties
    
    Returns:
        Dictionary of calendar processing settings
    """
    settings = {}
    
    # Core booking functionality
    bookable = device_data.get('Bookable', False)
    if isinstance(bookable, str):
        bookable = bookable.lower() in ['true', '1', 'on', 'yes', 'y']
    settings['bookable'] = bool(bookable)
    
    if settings['bookable']:
        # Booking policies
        settings['allowConflicts'] = bool(device_data.get('AllowConflicts', False))
        settings['bookingWindowInDays'] = int(device_data.get('BookingWindowInDays', 90))
        settings['maximumDurationInMinutes'] = int(device_data.get('MaximumDurationInMinutes', 1440))
        
        # Recurring meetings
        recurring = device_data.get('RecurringAllowed', False)
        if isinstance(recurring, str):
            recurring = recurring.lower() in ['true', '1', 'on', 'yes', 'y']
        settings['allowRecurringMeetings'] = bool(recurring)
        
        # Approvers/Delegates
        approvers = device_data.get('Approvers', [])
        if isinstance(approvers, str):
            approvers = [a.strip() for a in approvers.split(',') if a.strip()]
        settings['resourceDelegates'] = approvers if approvers else []
        
        # Working hours
        work_hours = device_data.get('WorkHours')
        if work_hours:
            settings['scheduleOnlyDuringWorkHours'] = True
        else:
            settings['scheduleOnlyDuringWorkHours'] = False
        
        # Additional response message
        settings['additionalResponse'] = """IMPORTANT: Check the meeting status in your calendar:
- ACCEPTED = Equipment is reserved for you
- DECLINED = Equipment is NOT available - DELETE this calendar entry immediately
- TENTATIVE = Awaiting approval from fleet manager

Always cancel bookings you no longer need so others can use the equipment."""
    
    return settings


# Main integration function for the Function App
async def update_equipment_mailbox_calendar_processing(
    mailbox_email: str, 
    device_data: Dict[str, Any],
    app_id: str,
    cert_thumbprint: str,
    organization: str
) -> Dict[str, Any]:
    """
    Update calendar processing settings for an equipment mailbox.
    
    This function bridges the gap between Graph API (which handles basic mailbox settings)
    and Exchange PowerShell (which handles calendar processing settings).
    """
    try:
        # Convert device data to calendar processing settings
        settings = create_equipment_mailbox_settings(device_data)
        
        # Skip if not bookable to avoid unnecessary PowerShell execution
        if not settings.get('bookable', False):
            logging.info(f"Device not bookable, skipping calendar processing for {mailbox_email}")
            return {'success': True, 'message': 'Skipped - not bookable'}
        
        # Execute PowerShell to configure calendar processing
        ps_executor = ExchangePowerShellExecutor(app_id, cert_thumbprint, organization)
        result = await ps_executor.set_calendar_processing_async(mailbox_email, settings)
        
        return result
        
    except Exception as e:
        logging.error(f"Error updating calendar processing for {mailbox_email}: {e}")
        return {'success': False, 'error': str(e)}