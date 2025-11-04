import azure.functions as func
import logging
import json
import os
import subprocess
from mygeotab import API
from azure.keyvault.secrets import SecretClient
from azure.keyvault.certificates import CertificateClient
from azure.identity import DefaultAzureCredential, CertificateCredential
from datetime import datetime
import msal
from msgraph import GraphServiceClient
from msgraph.generated.users.item.mailbox_settings.mailbox_settings_request_builder import MailboxSettingsRequestBuilder
from msgraph.generated.models.user import User
from msgraph.generated.models.mailbox_settings import MailboxSettings
from msgraph.generated.models.locale_info import LocaleInfo
import base64
import tempfile
import asyncio
from exchange_powershell_linux import update_equipment_mailbox_calendar_processing

def ensure_powershell_available():
    """Install PowerShell Core if not available in the Azure Functions environment."""
    try:
        # Check if PowerShell is already available
        result = subprocess.run(['pwsh', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logging.info(f"PowerShell Core already available: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logging.warning(f"Error checking PowerShell availability: {e}")
    
    # PowerShell not found, try to install it
    logging.info("PowerShell Core not found, attempting to install...")
    
    try:
        # Install PowerShell Core using wget and dpkg (for Debian-based Azure Functions)
        install_commands = [
            # Download the PowerShell package
            "wget -q https://github.com/PowerShell/PowerShell/releases/download/v7.4.0/powershell_7.4.0-1.deb_amd64.deb -O /tmp/powershell.deb",
            # Install dependencies
            "apt-get update -qq",
            "apt-get install -y -qq libc6 libgcc1 libgssapi-krb5-2 liblttng-ust0 libstdc++6 libunwind8 libuuid1 zlib1g libicu67 || apt-get install -y -qq libc6 libgcc1 libgssapi-krb5-2 liblttng-ust1 libstdc++6 libunwind8 libuuid1 zlib1g libicu72",
            # Install PowerShell
            "dpkg -i /tmp/powershell.deb",
            # Fix any broken dependencies
            "apt-get install -f -y -qq"
        ]
        
        for cmd in install_commands:
            logging.info(f"Running: {cmd}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logging.warning(f"Command failed (continuing): {cmd}")
                logging.warning(f"Error: {result.stderr}")
            else:
                logging.info(f"Command succeeded: {cmd}")
        
        # Test if PowerShell is now available
        result = subprocess.run(['pwsh', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logging.info(f"PowerShell Core successfully installed: {result.stdout.strip()}")
            return True
        else:
            logging.error("PowerShell installation failed - executable not found after installation")
            return False
            
    except Exception as e:
        logging.error(f"Failed to install PowerShell Core: {e}")
        return False

def update_equipment_mailbox_calendar_processing_containerapp(access_token, mailbox_email, device_name):
    """
    Update equipment mailbox calendar processing using Azure Container App with PowerShell.
    This is the scalable solution that actually works for Exchange Online.
    """
    try:
        import requests
        import base64
        
        # Azure Container App endpoint
        container_app_url = os.environ.get('CONTAINER_APP_URL', 'https://exchange-calendar-processor.icydune-12345.eastus.azurecontainerapps.io')
        
        # Get certificate data from Key Vault
        cert_secret = key_vault_client.get_secret('powershell-cert-data')
        certificate_data = cert_secret.value
        
        # Prepare request payload
        payload = {
            'mailboxEmail': mailbox_email,
            'deviceName': device_name,
            'tenantId': ENTRA_TENANT_ID or 'your-tenant-id',
            'clientId': ENTRA_CLIENT_ID,
            'certificateData': certificate_data
        }
        
        # Call Container App
        response = requests.post(
            f"{container_app_url}/process-mailbox",
            json=payload,
            timeout=60,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"Successfully processed calendar settings via Container App for {mailbox_email}")
            return {
                'success': True,
                'method': 'azure_container_app_powershell',
                'mailbox': mailbox_email,
                'device': device_name,
                'details': result
            }
        else:
            logging.error(f"Container App error: {response.status_code} - {response.text}")
            return {
                'success': False,
                'method': 'azure_container_app_powershell',
                'error': f"Container App error: {response.status_code} - {response.text}",
                'mailbox': mailbox_email,
                'device': device_name
            }
            
    except Exception as e:
        logging.error(f"Error calling Container App for {mailbox_email}: {e}")
        return {
            'success': False,
            'method': 'azure_container_app_powershell',
            'error': str(e),
            'mailbox': mailbox_email,
            'device': device_name
        }

app = func.FunctionApp()

app = func.FunctionApp()

# Test route to verify loading
@app.route(route="test1", auth_level=func.AuthLevel.ANONYMOUS)
def test1(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("Test 1 works", status_code=200)

@app.route(route="system-info", auth_level=func.AuthLevel.ANONYMOUS)
def system_info(req: func.HttpRequest) -> func.HttpResponse:
    """Get system information about the Azure Functions environment."""
    
    try:
        info = {}
        
        # Check OS information
        try:
            result = subprocess.run(['uname', '-a'], capture_output=True, text=True, timeout=10)
            info['uname'] = result.stdout.strip()
        except Exception as e:
            info['uname_error'] = str(e)
        
        # Check Linux distribution
        try:
            result = subprocess.run(['cat', '/etc/os-release'], capture_output=True, text=True, timeout=10)
            info['os_release'] = result.stdout.strip()
        except Exception as e:
            info['os_release_error'] = str(e)
            
        # Check available package managers
        package_managers = ['apt-get', 'yum', 'apk', 'dnf']
        for pm in package_managers:
            try:
                result = subprocess.run([pm, '--version'], capture_output=True, text=True, timeout=10)
                info[f'{pm}_available'] = result.returncode == 0
                if result.returncode == 0:
                    info[f'{pm}_version'] = result.stdout.strip()
            except Exception:
                info[f'{pm}_available'] = False
        
        # Check if we have sudo permissions
        try:
            result = subprocess.run(['sudo', '-n', 'echo', 'test'], capture_output=True, text=True, timeout=10)
            info['sudo_available'] = result.returncode == 0
        except Exception:
            info['sudo_available'] = False
            
        # Check available shell commands
        commands = ['wget', 'curl', 'dpkg', 'which']
        for cmd in commands:
            try:
                result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=10)
                info[f'{cmd}_available'] = result.returncode == 0
                if result.returncode == 0:
                    info[f'{cmd}_path'] = result.stdout.strip()
            except Exception:
                info[f'{cmd}_available'] = False
        
        return func.HttpResponse(
            json.dumps(info, indent=2),
            status_code=200,
            mimetype="application/json"
        )
            
    except Exception as e:
        logging.error(f"System info error: {e}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
def install_powershell(req: func.HttpRequest) -> func.HttpResponse:
    """Attempt to install PowerShell Core in the Azure Functions environment."""
    
    try:
        success = ensure_powershell_available()
        
        if success:
            # Test PowerShell functionality
            result = subprocess.run(['pwsh', '--version'], capture_output=True, text=True, timeout=10)
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "message": "PowerShell Core is now available",
                    "version": result.stdout.strip()
                }),
                status_code=200,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "message": "Failed to install PowerShell Core"
                }),
                status_code=500,
                mimetype="application/json"
            )
            
    except Exception as e:
        logging.error(f"Install PowerShell error: {e}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )

# Diagnostic endpoint to test PowerShell integration
@app.route(route="test-powershell", auth_level=func.AuthLevel.ANONYMOUS)
def test_powershell(req: func.HttpRequest) -> func.HttpResponse:
    """Test PowerShell Core and Exchange Online module availability"""
    
    results = {}
    
    try:
        # Test 1: Check if PowerShell Core is available
        logging.info("Testing PowerShell Core availability...")
        
        # Try different PowerShell executables
        ps_commands = ['pwsh', 'powershell', 'powershell.exe']
        ps_available = False
        ps_command = None
        
        for cmd in ps_commands:
            try:
                ps_result = subprocess.run([cmd, '--version'], 
                                         capture_output=True, text=True, timeout=30)
                if ps_result.returncode == 0:
                    ps_available = True
                    ps_command = cmd
                    break
            except FileNotFoundError:
                continue
            except Exception as e:
                logging.warning(f"Error testing {cmd}: {e}")
                continue
        
        results['powershell_core'] = {
            'available': ps_available,
            'command': ps_command,
            'tested_commands': ps_commands
        }
        
        if ps_available and ps_command:
            # Get version info
            ps_result = subprocess.run([ps_command, '--version'], 
                                     capture_output=True, text=True, timeout=30)
            results['powershell_core']['version'] = ps_result.stdout.strip()
        else:
            results['powershell_core']['error'] = 'No PowerShell executable found'
        
        # Test 2: Check Exchange Online module
        logging.info("Testing Exchange Online PowerShell module...")
        if ps_available and ps_command:
            module_test = subprocess.run([
                ps_command, '-c', 'Import-Module ExchangeOnlineManagement -Force; Get-Module ExchangeOnlineManagement'
            ], capture_output=True, text=True, timeout=30)
            
            results['exchange_module'] = {
                'available': 'ExchangeOnlineManagement' in module_test.stdout,
                'output': module_test.stdout.strip(),
                'error': module_test.stderr.strip(),
                'returncode': module_test.returncode
            }
        else:
            results['exchange_module'] = {
                'available': False,
                'error': 'PowerShell not available to test Exchange module'
            }
        
        # Test 3: Check Key Vault access
        logging.info("Testing Key Vault access...")
        try:
            key_vault_url = KEY_VAULT_URL
            if key_vault_url and key_vault_client:
                # Try to access the certificate secret
                cert_secret = key_vault_client.get_secret('powershell-cert-data')
                
                results['key_vault'] = {
                    'accessible': True,
                    'certificate_found': len(cert_secret.value) > 0,
                    'certificate_length': len(cert_secret.value)
                }
            else:
                results['key_vault'] = {
                    'accessible': False,
                    'error': 'KEY_VAULT_URL not configured or client not available'
                }
        except Exception as kv_error:
            results['key_vault'] = {
                'accessible': False,
                'error': str(kv_error)
            }
        
        # Test 4: Check environment variables
        results['environment'] = {
            'ENTRA_CLIENT_ID': bool(ENTRA_CLIENT_ID),
            'KEY_VAULT_URL': bool(KEY_VAULT_URL),
            'USE_KEY_VAULT': str(USE_KEY_VAULT)
        }
        
        # Test 5: Try to import our PowerShell module
        try:
            from exchange_powershell_linux import ExchangePowerShellExecutor
            results['powershell_module'] = {
                'importable': True,
                'class_available': True
            }
        except ImportError as import_error:
            results['powershell_module'] = {
                'importable': False,
                'error': str(import_error)
            }
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "tests": results,
                "summary": {
                    "powershell_ready": results.get('powershell_core', {}).get('available', False),
                    "exchange_ready": results.get('exchange_module', {}).get('available', False),
                    "keyvault_ready": results.get('key_vault', {}).get('accessible', False),
                    "module_ready": results.get('powershell_module', {}).get('importable', False)
                }
            }, indent=2),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"PowerShell test failed: {e}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e),
                "tests": results
            }),
            status_code=500,
            mimetype="application/json"
        )

# Configuration
KEY_VAULT_URL = os.environ.get('KEY_VAULT_URL', '')  # e.g., https://fleetbridge-vault.vault.azure.net/
USE_KEY_VAULT = os.environ.get('USE_KEY_VAULT', 'false').lower() == 'true'

# Multi-tenant OAuth configuration
ENTRA_CLIENT_ID = os.environ.get('ENTRA_CLIENT_ID')
ENTRA_CLIENT_SECRET_NAME = os.environ.get('ENTRA_CLIENT_SECRET_NAME', 'EntraAppClientSecret')
ENTRA_AUTHORITY = "https://login.microsoftonline.com/organizations"
ENTRA_SCOPES = [
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/MailboxSettings.ReadWrite"
    # Note: offline_access is reserved and automatically included by Azure AD
    # Removed User.ReadWrite.All - not needed for calendar/mailbox settings only
]

# Initialize Key Vault client if enabled
key_vault_client = None
certificate_client = None
if USE_KEY_VAULT and KEY_VAULT_URL:
    try:
        credential = DefaultAzureCredential()
        key_vault_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
        certificate_client = CertificateClient(vault_url=KEY_VAULT_URL, credential=credential)
        logging.info('Key Vault clients initialized')
    except Exception as e:
        logging.error(f'Failed to initialize Key Vault clients: {e}')

# Rate limiting: Simple in-memory cache (per-instance)
# Key: IP address, Value: (request_count, window_start_time)
rate_limit_cache = {}
RATE_LIMIT_REQUESTS = 30  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds

def check_rate_limit(client_ip: str) -> tuple[bool, str]:
    """
    Check if client IP is within rate limits.
    Returns: (allowed: bool, message: str)
    """
    import time
    current_time = time.time()
    
    if client_ip in rate_limit_cache:
        count, window_start = rate_limit_cache[client_ip]
        
        # Reset window if expired
        if current_time - window_start > RATE_LIMIT_WINDOW:
            rate_limit_cache[client_ip] = (1, current_time)
            return (True, "")
        
        # Check if over limit
        if count >= RATE_LIMIT_REQUESTS:
            remaining_time = int(RATE_LIMIT_WINDOW - (current_time - window_start))
            logging.warning(f'Rate limit exceeded for IP {client_ip}. Count: {count}, Window: {window_start}')
            return (False, f"Rate limit exceeded. Try again in {remaining_time} seconds.")
        
        # Increment counter
        rate_limit_cache[client_ip] = (count + 1, window_start)
        return (True, "")
    else:
        # First request from this IP
        rate_limit_cache[client_ip] = (1, current_time)
        return (True, "")

def validate_api_key(api_key: str, client_ip: str = "unknown") -> tuple[bool, str]:
    """
    Validate API key by checking if corresponding secrets exist in Key Vault.
    
    Args:
        api_key: Client API key to validate
        client_ip: Client IP address for logging
    
    Returns:
        (valid: bool, error_message: str)
    """
    if not api_key:
        logging.warning(f'API key validation failed: No API key provided from IP {client_ip}')
        return (False, "API key is required")
    
    # Validate format: should be 32 character hex (UUID without dashes)
    if not isinstance(api_key, str) or len(api_key) != 32:
        logging.warning(f'API key validation failed: Invalid format from IP {client_ip}')
        return (False, "Invalid API key format")
    
    if not api_key.replace('-', '').isalnum():
        logging.warning(f'API key validation failed: Invalid characters from IP {client_ip}')
        return (False, "Invalid API key format")
    
    # Check if API key exists in Key Vault
    if not USE_KEY_VAULT or not key_vault_client:
        logging.error(f'API key validation failed: Key Vault not configured')
        return (False, "Key Vault not configured")
    
    try:
        # Try to get the database secret for this API key
        # If it doesn't exist, the API key is invalid
        secret_name = f'client-{api_key}-database'
        key_vault_client.get_secret(secret_name)
        
        # API key is valid
        logging.info(f'API key validation successful for client from IP {client_ip}')
        return (True, "")
        
    except Exception as e:
        # API key not found or other error
        error_str = str(e)
        
        # Log security event - potential unauthorized access attempt
        if 'not found' in error_str.lower() or 'does not exist' in error_str.lower():
            logging.warning(f'SECURITY: Invalid API key attempt from IP {client_ip}. API key does not exist in Key Vault.')
        else:
            logging.error(f'SECURITY: API key validation error from IP {client_ip}: {error_str}')
        
        # Return generic error (don't leak whether key exists)
        return (False, "Invalid API key")

def require_valid_api_key(req: func.HttpRequest) -> tuple[bool, str, str]:
    """
    Validate API key from request and check rate limits.
    
    Returns:
        (valid: bool, api_key: str, error_message: str)
    """
    # Get client IP for rate limiting and logging
    client_ip = req.headers.get('X-Forwarded-For', 'unknown')
    if ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    # Check rate limit first
    allowed, rate_limit_msg = check_rate_limit(client_ip)
    if not allowed:
        logging.warning(f'SECURITY: Rate limit exceeded from IP {client_ip}')
        return (False, "", rate_limit_msg)
    
    # Get API key from request body
    try:
        req_body = req.get_json()
        api_key = req_body.get('apiKey') or req_body.get('clientId')
    except:
        logging.warning(f'SECURITY: No JSON body in request from IP {client_ip}')
        return (False, "", "Invalid request format")
    
    # Validate API key
    valid, error_msg = validate_api_key(api_key, client_ip)
    
    if not valid:
        return (False, "", error_msg)
    
    return (True, api_key, "")

def get_client_credentials(api_key=None, database=None, username=None, password=None):
    """
    Get client credentials either from Key Vault (using API key) or from request parameters.
    
    Returns: (database, username, password) tuple or None if not found
    """
    if USE_KEY_VAULT and api_key and key_vault_client:
        # Option 2: Get credentials from Key Vault using API key
        try:
            # Store credentials in Key Vault with naming convention: client-{api_key}-database, etc.
            database_secret = key_vault_client.get_secret(f'client-{api_key}-database')
            username_secret = key_vault_client.get_secret(f'client-{api_key}-username')
            password_secret = key_vault_client.get_secret(f'client-{api_key}-password')
            
            return (database_secret.value, username_secret.value, password_secret.value)
        except Exception as e:
            logging.error(f'Failed to get credentials from Key Vault for API key {api_key}: {e}')
            return None
    else:
        # Option 1: Get credentials from request parameters
        if database and username and password:
            return (database, username, password)
        return None

def log_usage(database, operation, success, execution_time_ms):
    """
    Log usage for billing and monitoring.
    In production, this would write to a database or Application Insights.
    """
    usage_log = {
        'timestamp': datetime.utcnow().isoformat(),
        'database': database,
        'operation': operation,
        'success': success,
        'execution_time_ms': execution_time_ms
    }
    logging.info(f'USAGE: {json.dumps(usage_log)}')
    
    # TODO: In production, write to:
    # - Azure Table Storage (cheap, good for billing)
    # - Application Insights (already integrated)
    # - Azure SQL Database (if you need complex queries)

def get_client_secret():
    """Get Entra app client secret from Key Vault."""
    if not key_vault_client:
        raise ValueError("Key Vault not configured")
    
    secret = key_vault_client.get_secret(ENTRA_CLIENT_SECRET_NAME)
    return secret.value

def get_application_graph_token(api_key, tenant_id):
    """
    Get application access token for Microsoft Graph using certificate authentication.
    This uses application permissions (not delegated) to access all mailboxes.
    
    Args:
        api_key: Client API key (to retrieve certificate from Key Vault)
        tenant_id: Azure AD tenant ID for the client
    
    Returns:
        str: Valid access token for Microsoft Graph with application permissions
    
    Raises:
        ValueError: If certificate not found or authentication fails
    """
    logging.info(f'Getting application token for tenant {tenant_id}')
    
    try:
        # Get certificate from Key Vault (stored as base64-encoded PFX)
        logging.info(f'Retrieving certificate from Key Vault for client {api_key[:8]}...')
        cert_secret = key_vault_client.get_secret(f'client-{api_key}-app-certificate')
        cert_base64 = cert_secret.value
        logging.info(f'Certificate retrieved, length: {len(cert_base64)} chars')
        
        # Decode base64 to get PFX bytes
        import base64
        cert_bytes = base64.b64decode(cert_base64)
        logging.info(f'Certificate decoded, {len(cert_bytes)} bytes')
        
        # Write to temporary file (MSAL requires file path)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pfx') as cert_file:
            cert_file.write(cert_bytes)
            cert_path = cert_file.name
        
        logging.info(f'Certificate written to temp file: {cert_path}')
        
        try:
            # Create credential using certificate
            from azure.identity import CertificateCredential
            logging.info(f'Creating CertificateCredential for tenant {tenant_id}, client {ENTRA_CLIENT_ID}')
            
            credential = CertificateCredential(
                tenant_id=tenant_id,
                client_id=ENTRA_CLIENT_ID,
                certificate_path=cert_path
            )
            
            # Get token for Microsoft Graph
            logging.info('Requesting token from Microsoft Graph...')
            token = credential.get_token("https://graph.microsoft.com/.default")
            
            logging.info(f'✓ Successfully obtained application token for tenant {tenant_id}')
            return token.token
            
        finally:
            # Clean up temporary file
            import os
            if os.path.exists(cert_path):
                os.unlink(cert_path)
                logging.info('Cleaned up temporary certificate file')
                
    except Exception as e:
        logging.error(f'Failed to get application token: {type(e).__name__}: {e}')
        import traceback
        logging.error(f'Traceback: {traceback.format_exc()}')
        raise ValueError(f'Failed to authenticate with certificate: {str(e)}')

def get_delegated_graph_token(client_id):
    """
    Get fresh access token for Microsoft Graph using stored refresh token.
    This is called before each sync operation.
    
    Args:
        client_id: Unique client identifier (API key or database name)
    
    Returns:
        str: Valid access token for Microsoft Graph
    
    Raises:
        ValueError: If refresh token not found or token refresh fails
    """
    try:
        # Get refresh token and tenant ID from Key Vault
        refresh_token_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-refresh-token")
        tenant_id_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-tenant-id")
        
        refresh_token = refresh_token_secret.value
        tenant_id = tenant_id_secret.value
        
        # Get client secret
        client_secret = get_client_secret()
        
        # Create MSAL app with specific tenant
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        msal_app = msal.ConfidentialClientApplication(
            ENTRA_CLIENT_ID,
            authority=authority,
            client_credential=client_secret
        )
        
        # Acquire token using refresh token
        result = msal_app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=ENTRA_SCOPES
        )
        
        if "error" in result:
            logging.error(f"Token refresh error for client {client_id}: {result.get('error_description')}")
            raise ValueError(f"Failed to refresh token: {result.get('error_description')}")
        
        access_token = result.get('access_token')
        new_refresh_token = result.get('refresh_token')
        
        # Update refresh token if rotated
        if new_refresh_token and new_refresh_token != refresh_token:
            key_vault_client.set_secret(f"client-{client_id}-exchange-refresh-token", new_refresh_token)
            logging.info(f"Updated refresh token for client {client_id}")
        
        return access_token
        
    except Exception as e:
        logging.error(f"Failed to get delegated token for client {client_id}: {e}")
        raise ValueError(f"Exchange connection expired. Please reconnect in the Add-In. Details: {str(e)}")

# ============================================================================
# OAuth Endpoints (Multi-Tenant SaaS)
# ============================================================================

@app.route(route="authlogin", auth_level=func.AuthLevel.ANONYMOUS)
def oauth_login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Step 1: Redirect user to Microsoft consent page.
    
    Query params:
    - clientId: Unique identifier for the client (their API key or database name)
    """
    try:
        # Get client IP for security logging
        client_ip = req.headers.get('X-Forwarded-For', 'unknown')
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        # Check rate limit
        allowed, rate_limit_msg = check_rate_limit(client_ip)
        if not allowed:
            logging.warning(f'SECURITY: Rate limit exceeded on authlogin from IP {client_ip}')
            return func.HttpResponse(rate_limit_msg, status_code=429)
        
        client_id = req.params.get('clientId')
        if not client_id:
            return func.HttpResponse("Missing clientId parameter", status_code=400)
        
        # Validate API key (clientId is the API key)
        valid, error_msg = validate_api_key(client_id, client_ip)
        if not valid:
            return func.HttpResponse(
                f"Unauthorized: {error_msg}",
                status_code=401
            )
        
        # Generate random state to prevent CSRF
        import secrets
        state = secrets.token_urlsafe(32)
        
        # Encode client_id in state (in production, use Redis/Table Storage)
        state_with_client = f"{state}:{client_id}"
        
        # Build authorization URL
        redirect_uri = f"https://{os.environ.get('WEBSITE_HOSTNAME', 'localhost:7071')}/api/authcallback"
        
        from urllib.parse import urlencode
        # Use admin consent endpoint to grant BOTH delegated AND application permissions
        auth_params = {
            'client_id': ENTRA_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'state': state_with_client,
        }
        
        # Admin consent endpoint - grants all permissions (delegated + application)
        auth_url = f"{ENTRA_AUTHORITY}/adminconsent?{urlencode(auth_params)}"
        
        logging.info(f"Admin consent flow initiated for client: {client_id} from IP: {client_ip}")

        
        # Return redirect response
        return func.HttpResponse(
            status_code=302,
            headers={'Location': auth_url}
        )
        
    except Exception as e:
        logging.error(f"OAuth login error: {e}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)


@app.route(route="authcallback", auth_level=func.AuthLevel.ANONYMOUS)
def oauth_callback(req: func.HttpRequest) -> func.HttpResponse:
    """
    Step 2: Receive auth code from Microsoft and exchange for tokens.
    
    Query params:
    - code: Authorization code from Microsoft
    - state: State parameter (contains client_id)
    - error: Error code (if consent denied)
    """
    try:
        # Check for errors
        error = req.params.get('error')
        if error:
            error_desc = req.params.get('error_description', 'Unknown error')
            logging.error(f"OAuth error: {error} - {error_desc}")
            
            # Return user-friendly error page
            return func.HttpResponse(
                f"""
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Connection Failed</title>
                </head>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h1 style="color: #d32f2f;">❌ Connection Failed</h1>
                    <p>{error_desc}</p>
                    <p>Please close this window and try again.</p>
                </body>
                </html>
                """,
                mimetype="text/html",
                status_code=400
            )
        
        # Check if this is admin consent callback (admin_consent=True)
        admin_consent = req.params.get('admin_consent')
        tenant = req.params.get('tenant')
        state = req.params.get('state')
        
        if not state:
            return func.HttpResponse("Missing state parameter", status_code=400)
        
        # Extract client_id from state
        try:
            state_nonce, client_id = state.split(':', 1)
        except:
            return func.HttpResponse("Invalid state parameter", status_code=400)
        
        # Handle admin consent response
        if admin_consent == 'True' and tenant:
            logging.info(f"Admin consent granted for client: {client_id}, tenant: {tenant}")
            
            # Store tenant ID in Key Vault (needed for certificate-based auth)
            if key_vault_client:
                tenant_secret_name = f"client-{client_id}-exchange-tenant-id"
                key_vault_client.set_secret(tenant_secret_name, tenant)
                logging.info(f"Stored tenant ID for client {client_id} in Key Vault")
            
            # Return success page
            return func.HttpResponse(
                f"""
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Connected!</title>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            padding: 40px;
                            text-align: center;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            margin: 0;
                        }}
                        .container {{
                            background: white;
                            color: #333;
                            padding: 40px;
                            border-radius: 12px;
                            max-width: 600px;
                            margin: 0 auto;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    }}
                    h1 {{ color: #10b981; margin-bottom: 20px; }}
                    .info {{ 
                        background: #f3f4f6; 
                        padding: 20px; 
                        border-radius: 8px; 
                        margin: 20px 0;
                        text-align: left;
                    }}
                    .info strong {{ color: #667eea; }}
                    button {{
                        background: #667eea;
                        color: white;
                        border: none;
                        padding: 12px 30px;
                        border-radius: 6px;
                        font-size: 16px;
                        cursor: pointer;
                        margin-top: 20px;
                    }}
                    button:hover {{ background: #5568d3; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✅ Admin Consent Granted!</h1>
                    <p>FleetBridge now has permission to manage equipment mailboxes in Exchange Online.</p>
                    
                    <div class="info">
                        <p><strong>Organization ID:</strong> {tenant}</p>
                        <p><strong>Permissions Granted:</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>Read and write calendars (all mailboxes)</li>
                            <li>Read and write mailbox settings (all mailboxes)</li>
                        </ul>
                    </div>
                    
                    <p>You can now close this window and start syncing devices.</p>
                    <button onclick="window.close()">Close Window</button>
                    
                    <script>
                        // Auto-close after 5 seconds
                        setTimeout(() => window.close(), 5000);
                    </script>
                </div>
            </body>
            </html>
            """,
            mimetype="text/html",
            status_code=200
        )
        
        # If admin_consent is False or missing, consent was denied
        logging.warning(f"Admin consent denied for client: {client_id}")
        return func.HttpResponse(
            """
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Consent Denied</title>
            </head>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #d32f2f;">❌ Admin Consent Denied</h1>
                <p>FleetBridge requires admin consent to manage equipment mailboxes.</p>
                <p>Please contact your administrator or try again.</p>
                <button onclick="window.close()" style="background: #667eea; color: white; border: none; padding: 12px 30px; border-radius: 6px; font-size: 16px; cursor: pointer; margin-top: 20px;">Close Window</button>
            </body>
            </html>
            """,
            mimetype="text/html",
            status_code=403
        )
        
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return func.HttpResponse(
            f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Error</title>
            </head>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #d32f2f;">❌ Error</h1>
                <p>{str(e)}</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            mimetype="text/html",
            status_code=500
        )


@app.route(route="authstatus", auth_level=func.AuthLevel.ANONYMOUS)
def auth_status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Check if a client has connected their Exchange account.
    
    POST body:
    {
        "clientId": "client-api-key-or-database"
    }
    """
    try:
        # Get client IP for security logging
        client_ip = req.headers.get('X-Forwarded-For', 'unknown')
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        # Check rate limit
        allowed, rate_limit_msg = check_rate_limit(client_ip)
        if not allowed:
            logging.warning(f'SECURITY: Rate limit exceeded on authstatus from IP {client_ip}')
            return func.HttpResponse(
                json.dumps({"connected": False, "error": rate_limit_msg}),
                status_code=429,
                mimetype="application/json"
            )
        
        req_body = req.get_json()
        client_id = req_body.get('clientId')
        
        if not client_id:
            return func.HttpResponse(
                json.dumps({"connected": False, "error": "Missing clientId"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate API key
        valid, error_msg = validate_api_key(client_id, client_ip)
        if not valid:
            return func.HttpResponse(
                json.dumps({"connected": False, "error": error_msg}),
                status_code=401,
                mimetype="application/json"
            )
        
        # Check if refresh token exists
        if key_vault_client:
            try:
                refresh_token_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-refresh-token")
                tenant_id_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-tenant-id")
                
                # Try to get user email (optional)
                user_email = "Unknown"
                try:
                    email_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-user-email")
                    user_email = email_secret.value
                except:
                    pass
                
                logging.info(f"Auth status check: Client {client_id} is connected from IP {client_ip}")
                return func.HttpResponse(
                    json.dumps({
                        "connected": True,
                        "userEmail": user_email,
                        "tenantId": tenant_id_secret.value
                    }),
                    mimetype="application/json"
                )
            except Exception as e:
                logging.info(f"Client {client_id} not connected: {e}")
                return func.HttpResponse(
                    json.dumps({"connected": False}),
                    mimetype="application/json"
                )
        else:
            return func.HttpResponse(
                json.dumps({"connected": False, "error": "Key Vault not configured"}),
                status_code=500,
                mimetype="application/json"
            )
        
    except Exception as e:
        logging.error(f"Auth status check error: {e}")
        return func.HttpResponse(
            json.dumps({"connected": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

# ============================================================================
# MyGeotab Endpoints
# ============================================================================

@app.route(route="update-device-properties", auth_level=func.AuthLevel.ANONYMOUS)
def update_device_properties(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function to update MyGeotab device custom properties.
    
    Supports two authentication modes:
    
    Mode 1 - Direct credentials (for starting out):
    {
        "database": "database_name",
        "username": "user@example.com",
        "password": "password",
        "deviceId": "b1",
        "properties": {...}
    }
    
    Mode 2 - API key (for production multi-tenant):
    {
        "apiKey": "client-api-key-here",
        "deviceId": "b1",
        "properties": {...}
    }
    """
    start_time = datetime.utcnow()
    logging.info('Update device properties function triggered')
    
    try:
        # Validate API key and rate limit
        valid, api_key, error_msg = require_valid_api_key(req)
        if not valid:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": error_msg
                }),
                status_code=401 if "Invalid API key" in error_msg else 429,
                mimetype="application/json"
            )
        
        # Parse request body
        req_body = req.get_json()
        
        # Get credentials (from Key Vault using API key)
        database = req_body.get('database')
        username = req_body.get('username')
        password = req_body.get('password')
        
        credentials = get_client_credentials(api_key, database, username, password)
        
        if not credentials:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Invalid credentials or API key"
                }),
                status_code=401,
                mimetype="application/json"
            )
        
        database, username, password = credentials
        
        # Get other parameters
        device_id = req_body.get('deviceId')
        properties = req_body.get('properties')
        
        # Validate required parameters
        if not all([device_id, properties]):
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Missing required parameters: deviceId, properties"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Connect to MyGeotab
        logging.info(f'Connecting to MyGeotab database: {database}')
        api = API(username=username, password=password, database=database)
        api.authenticate()
        
        # Fetch the device
        logging.info(f'Fetching device: {device_id}')
        devices = api.get('Device', search={'id': device_id})
        if not devices:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": f"Device not found: {device_id}"
                }),
                status_code=404,
                mimetype="application/json"
            )
        
        device = devices[0]
        logging.info(f'Device retrieved: {device.get("name")}')
        
        # Fetch property definitions
        logging.info('Fetching property definitions')
        all_properties = api.get('Property')
        
        # Property name mapping
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
        
        logging.info(f'Found {len(prop_lookup)} property definitions')
        
        # Build updated customProperties array
        custom_properties = device.get('customProperties', [])
        
        for key, value in properties.items():
            if key not in prop_lookup:
                logging.warning(f'Property not found: {key}')
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
                logging.info(f'Updating property: {key} = {value}')
                custom_properties[existing_index] = property_value
            else:
                # Add new
                logging.info(f'Adding property: {key} = {value}')
                custom_properties.append(property_value)
        
        # Update device customProperties
        device['customProperties'] = custom_properties
        
        # Call Set to update the device
        logging.info('Calling Set to update device')
        api.set('Device', device)
        
        logging.info('Device updated successfully')
        
        # Log usage for billing
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_usage(database, 'update-device-properties', True, execution_time)
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "message": f"Device {device.get('name')} updated successfully",
                "database": database,
                "deviceId": device_id
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f'Error updating device: {str(e)}', exc_info=True)
        
        # Log failed usage
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        if 'database' in locals():
            log_usage(database, 'update-device-properties', False, execution_time)
        
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint for monitoring.
    """
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "keyVaultEnabled": USE_KEY_VAULT
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="test-oauth", auth_level=func.AuthLevel.ANONYMOUS)
def test_oauth(req: func.HttpRequest) -> func.HttpResponse:
    """Test endpoint to verify OAuth code is deployed."""
    return func.HttpResponse(
        json.dumps({
            "message": "OAuth endpoints deployed!",
            "entraClientId": ENTRA_CLIENT_ID,
            "entraConfigured": bool(ENTRA_CLIENT_ID)
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="test-app-token", auth_level=func.AuthLevel.ANONYMOUS)
async def test_app_token(req: func.HttpRequest) -> func.HttpResponse:
    """Test endpoint to verify application token and mailbox lookup."""
    try:
        api_key = "2b25f16552be4781a5a109b318ccb10c"  # Garage of Awesome
        tenant_id = "a8713c4a-df53-4daf-8420-4dc43c792b68"
        test_email = "cy1b215b5229@garageofawesome.com.au"
        
        # Get application token
        logging.info("Getting application token...")
        access_token = get_application_graph_token(api_key, tenant_id)
        logging.info(f"Token obtained, length: {len(access_token)}")
        
        # Create Graph client
        logging.info("Creating Graph client...")
        graph_client = await get_delegated_graph_client(access_token)
        
        # Try to find mailbox
        logging.info(f"Looking up mailbox: {test_email}")
        user = await graph_client.users.by_user_id(test_email).get()
        
        # Try to UPDATE mailbox settings (this is where permission issues occur)
        logging.info("Attempting to update mailbox settings...")
        from msgraph.generated.models.mailbox_settings import MailboxSettings
        from msgraph.generated.models.locale_info import LocaleInfo
        
        settings = MailboxSettings()
        settings.time_zone = "AUS Eastern Standard Time"
        settings.language = LocaleInfo(
            locale="en-AU",
            display_name="English (Australia)"
        )
        
        try:
            await graph_client.users.by_user_id(test_email).mailbox_settings.patch(settings)
            update_success = True
            update_error = None
        except Exception as update_ex:
            update_success = False
            update_error = str(update_ex)
            logging.error(f"Failed to update mailbox: {update_error}")
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "token_length": len(access_token),
                "mailbox_found": user is not None,
                "mailbox_id": user.id if user else None,
                "mailbox_upn": user.user_principal_name if user else None,
                "mailbox_display_name": user.display_name if user else None,
                "update_success": update_success,
                "update_error": update_error
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        import traceback
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }),
            status_code=500,
            mimetype="application/json"
        )


# ========================================================================
# EXCHANGE SYNC ENDPOINT
# ========================================================================

def get_graph_credential():
    """
    Get Microsoft Graph credential using certificate from Key Vault.
    Returns CertificateCredential for Graph API authentication.
    """
    tenant_id = os.environ.get('ENTRA_TENANT_ID')
    client_id = os.environ.get('ENTRA_CLIENT_ID')
    cert_name = os.environ.get('ENTRA_CERT_NAME', 'FleetBridge-Exchange-Cert')
    
    if not all([tenant_id, client_id, KEY_VAULT_URL]):
        raise ValueError("Missing required environment variables: ENTRA_TENANT_ID, ENTRA_CLIENT_ID, or KEY_VAULT_URL")
    
    try:
        # Get certificate from Key Vault
        credential = DefaultAzureCredential()
        cert_client = CertificateClient(vault_url=KEY_VAULT_URL, credential=credential)
        
        # Download certificate with private key
        cert_bundle = cert_client.get_certificate(cert_name)
        secret_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
        cert_secret = secret_client.get_secret(cert_name)
        
        # The secret value contains the PFX in base64
        pfx_bytes = base64.b64decode(cert_secret.value)
        
        # Write to temporary file (Azure Functions have temp storage)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pfx') as temp_cert:
            temp_cert.write(pfx_bytes)
            temp_cert_path = temp_cert.name
        
        # Create certificate credential
        cert_credential = CertificateCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            certificate_path=temp_cert_path
        )
        
        logging.info('Successfully created Graph credential from Key Vault certificate')
        return cert_credential
        
    except Exception as e:
        logging.error(f'Failed to get Graph credential: {e}')
        raise


async def get_graph_client():
    """
    Get authenticated Microsoft Graph client using certificate (application permissions).
    DEPRECATED: Use get_delegated_graph_client() for SaaS multi-tenant setup.
    """
    credential = get_graph_credential()
    return GraphServiceClient(credentials=credential, scopes=['https://graph.microsoft.com/.default'])


async def get_delegated_graph_client(access_token):
    """
    Get authenticated Microsoft Graph client using delegated access token.
    This is the preferred method for multi-tenant SaaS.
    
    Args:
        access_token: Valid access token obtained from get_delegated_graph_token()
    
    Returns:
        GraphServiceClient configured with the access token
    """
    from azure.core.credentials import AccessToken
    from datetime import datetime, timedelta
    
    class StaticTokenCredential:
        """Simple credential that returns a static access token."""
        def __init__(self, token):
            self.token = token
        
        def get_token(self, *scopes, **kwargs):
            # Return AccessToken with token and expiry (1 hour from now)
            return AccessToken(self.token, int((datetime.now() + timedelta(hours=1)).timestamp()))
    
    credential = StaticTokenCredential(access_token)
    return GraphServiceClient(credentials=credential)


def convert_to_windows_timezone(tz_string):
    """
    Convert IANA timezone to Windows timezone ID.
    Focus on Australian timezones.
    """
    if not tz_string:
        return os.environ.get('DEFAULT_TIMEZONE', 'AUS Eastern Standard Time')
    
    tz = tz_string.strip()
    
    # If already Windows format, return as-is
    known_windows_tz = [
        'AUS Eastern Standard Time', 'E. Australia Standard Time',
        'Cen. Australia Standard Time', 'AUS Central Standard Time',
        'Tasmania Standard Time', 'W. Australia Standard Time',
        'Lord Howe Standard Time', 'Aus Central W. Standard Time'
    ]
    if tz in known_windows_tz:
        return tz
    
    # IANA to Windows mapping
    iana_to_windows = {
        'Australia/Sydney': 'AUS Eastern Standard Time',
        'Australia/Melbourne': 'AUS Eastern Standard Time',
        'Australia/Canberra': 'AUS Eastern Standard Time',
        'Australia/Brisbane': 'E. Australia Standard Time',
        'Australia/Hobart': 'Tasmania Standard Time',
        'Australia/Adelaide': 'Cen. Australia Standard Time',
        'Australia/Darwin': 'AUS Central Standard Time',
        'Australia/Perth': 'W. Australia Standard Time',
        'Australia/Broken_Hill': 'Cen. Australia Standard Time',
        'Australia/Lord_Howe': 'Lord Howe Standard Time',
        'Australia/Eucla': 'Aus Central W. Standard Time',
    }
    
    if tz in iana_to_windows:
        return iana_to_windows[tz]
    
    # Substring matching as fallback
    tz_lower = tz.lower()
    if any(x in tz_lower for x in ['sydney', 'melbourne', 'canberra', 'nsw', 'vic', 'act']):
        return 'AUS Eastern Standard Time'
    if any(x in tz_lower for x in ['brisbane', 'qld', 'queensland']):
        return 'E. Australia Standard Time'
    if any(x in tz_lower for x in ['hobart', 'tas', 'tasmania']):
        return 'Tasmania Standard Time'
    if any(x in tz_lower for x in ['adelaide', 'south australia', 'broken']):
        return 'Cen. Australia Standard Time'
    if any(x in tz_lower for x in ['darwin', 'nt', 'northern territory']):
        return 'AUS Central Standard Time'
    if any(x in tz_lower for x in ['perth', 'wa', 'western australia']):
        return 'W. Australia Standard Time'
    
    return os.environ.get('DEFAULT_TIMEZONE', 'AUS Eastern Standard Time')


async def find_equipment_mailbox(graph_client, primary_smtp, alias):
    """
    Find an equipment mailbox by primary SMTP address or alias.
    Returns user object if found, None otherwise.
    """
    try:
        # Try direct lookup by UPN/primary SMTP
        if primary_smtp and '@' in primary_smtp:
            try:
                user = await graph_client.users.by_user_id(primary_smtp).get()
                if user:
                    logging.info(f'Found mailbox via direct lookup: {primary_smtp}')
                    return user
            except Exception as e:
                logging.debug(f'Direct lookup failed for {primary_smtp}: {e}')
        
        # Try filter by mail
        if primary_smtp:
            try:
                result = await graph_client.users.get(
                    filter=f"mail eq '{primary_smtp}'",
                    top=1
                )
                if result and result.value and len(result.value) > 0:
                    logging.info(f'Found mailbox via mail filter: {primary_smtp}')
                    return result.value[0]
            except Exception as e:
                logging.debug(f'Mail filter failed for {primary_smtp}: {e}')
        
        # Try filter by proxyAddresses
        if primary_smtp:
            try:
                result = await graph_client.users.get(
                    filter=f"proxyAddresses/any(p:p eq 'smtp:{primary_smtp}')",
                    top=1
                )
                if result and result.value and len(result.value) > 0:
                    logging.info(f'Found mailbox via proxyAddresses: {primary_smtp}')
                    return result.value[0]
            except Exception as e:
                logging.debug(f'ProxyAddresses filter failed for {primary_smtp}: {e}')
        
        logging.info(f'Mailbox not found: {primary_smtp}')
        return None
        
    except Exception as e:
        logging.error(f'Error finding mailbox: {e}')
        return None


async def update_equipment_mailbox(graph_client, device, equipment_domain, access_token, app_id=None, key_vault_url=None):
    """
    Update an equipment mailbox based on MyGeotab device data.
    Uses Graph API for basic settings and PowerShell for calendar processing.
    Does NOT create mailboxes - only updates existing ones.
    
    Args:
        graph_client: Microsoft Graph client
        device: MyGeotab device dict
        equipment_domain: Email domain for equipment mailboxes
        access_token: OAuth access token for EWS authentication
        app_id: Application ID for PowerShell authentication
        key_vault_url: Key Vault URL containing certificate for PowerShell authentication
    """
    serial_number = device.get('SerialNumber', '').lower()
    if not serial_number:
        logging.warning(f"Device {device.get('Name')} has no serial number, skipping")
        return {'success': False, 'reason': 'no_serial_number'}
    
    alias = serial_number
    primary_smtp = f"{alias}@{equipment_domain}"
    display_name = device.get('Name', f"Equipment {alias}")
    
    logging.info(f"Processing device: {display_name} ({primary_smtp})")
    
    # Find existing mailbox
    mailbox = await find_equipment_mailbox(graph_client, primary_smtp, alias)
    
    if not mailbox:
        logging.info(f"Mailbox not found for {primary_smtp} - skipping (no auto-creation)")
        return {'success': False, 'reason': 'mailbox_not_found', 'email': primary_smtp}
    
    logging.info(f"Updating mailbox: {primary_smtp}")
    
    try:
        # Update display name using Graph API (this works fine)
        if display_name:
            user_update = User()
            user_update.display_name = display_name
            await graph_client.users.by_user_id(mailbox.id).patch(user_update)
        
        # Update user properties (State/Province for directory) using Graph API
        state = device.get('StateOrProvince')
        if state:
            user_state_update = User()
            user_state_update.state = state
            await graph_client.users.by_user_id(mailbox.id).patch(user_state_update)
        
        # Update mailbox settings (timezone, language) using Graph API
        # IMPORTANT: This requires ApplicationImpersonation role in Exchange Online for resource mailboxes
        # See EXCHANGE_IMPERSONATION_SETUP.md for configuration instructions
        timezone = convert_to_windows_timezone(device.get('TimeZone'))
        language = device.get('MailboxLanguage', 'en-AU')
        
        logging.info(f"Updating mailbox settings for {primary_smtp}: timezone={timezone}, language={language}")
        
        mailbox_settings_update = MailboxSettings()
        mailbox_settings_update.time_zone = timezone
        locale_info = LocaleInfo()
        locale_info.locale = language
        mailbox_settings_update.language = locale_info
        
        await graph_client.users.by_user_id(mailbox.id).mailbox_settings.patch(mailbox_settings_update)
        logging.info(f"✓ Successfully updated mailbox settings for {primary_smtp}")
        
        # Calendar processing settings using Azure Container App with PowerShell (SCALABLE SOLUTION!)
        # This replaces the non-functional PowerShell integration with a scalable Container App
        if app_id and key_vault_url:
            try:
                logging.info(f"Updating calendar processing settings for {primary_smtp} via Container App")
                ps_result = update_equipment_mailbox_calendar_processing_containerapp(
                    access_token,
                    primary_smtp, 
                    device['name']
                )
                
                if ps_result.get('success'):
                    logging.info(f"✓ Successfully updated calendar processing for {primary_smtp} via Container App")
                else:
                    logging.warning(f"⚠️ Failed to update calendar processing for {primary_smtp}: {ps_result.get('error', 'Unknown error')}")
                    # Don't fail the entire update if PowerShell fails - Graph updates are still valuable
                    
            except Exception as ps_error:
                logging.error(f"Error executing PowerShell for {primary_smtp}: {ps_error}")
                # Continue with the update even if PowerShell fails
        else:
            logging.warning("PowerShell credentials not provided - skipping calendar processing settings")
        
        logging.info(f"Successfully updated mailbox: {primary_smtp}")
        return {'success': True, 'email': primary_smtp, 'displayName': display_name}
        
    except Exception as e:
        logging.error(f"Error updating mailbox {primary_smtp}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {'success': False, 'reason': 'update_failed', 'error': str(e), 'email': primary_smtp}


@app.route(route="sync-to-exchange", auth_level=func.AuthLevel.ANONYMOUS)
async def sync_to_exchange(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sync MyGeotab devices to Exchange Online equipment mailboxes.
    
    Request body:
    {
        "apiKey": "client-api-key",  // Required
        "maxDevices": 0  // Optional: limit for testing
    }
    
    This endpoint:
    1. Fetches devices from MyGeotab
    2. For each device with a serial number:
       - Finds existing Exchange mailbox (by serial@domain)
       - Updates mailbox settings, calendar config, regional settings
       - Does NOT create new mailboxes (must be pre-created)
    """
    start_time = datetime.utcnow()
    logging.info('Sync to Exchange function triggered')
    
    try:
        # Validate API key and rate limit
        valid, api_key, error_msg = require_valid_api_key(req)
        if not valid:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": error_msg
                }),
                status_code=401 if "Invalid API key" in error_msg else 429,
                mimetype="application/json"
            )
        
        # Parse request body
        req_body = req.get_json()
        max_devices = req_body.get('maxDevices', 0)
        
        # Get MyGeotab credentials from Key Vault using API key
        credentials = get_client_credentials(api_key, None, None, None)
        
        if not credentials:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Invalid credentials or API key"
                }),
                status_code=401,
                mimetype="application/json"
            )
        
        database, username, password = credentials
        
        # Get equipment domain from Key Vault (per-client configuration)
        try:
            domain_secret = key_vault_client.get_secret(f'client-{api_key}-equipment-domain')
            equipment_domain = domain_secret.value
        except Exception as e:
            error_str = str(e)
            if 'not found' in error_str.lower():
                return func.HttpResponse(
                    json.dumps({
                        "success": False,
                        "error": "Equipment domain not configured for this client. Please contact support."
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
            else:
                logging.error(f'Error retrieving equipment domain: {error_str}')
                return func.HttpResponse(
                    json.dumps({
                        "success": False,
                        "error": "Error retrieving client configuration"
                    }),
                    status_code=500,
                    mimetype="application/json"
                )
        
        # Connect to MyGeotab
        logging.info(f'Connecting to MyGeotab database: {database}')
        api = API(username=username, password=password, database=database)
        api.authenticate()
        
        # Fetch devices
        logging.info('Fetching devices from MyGeotab')
        devices_raw = api.get('Device')
        
        # Fetch property catalog for normalization
        properties_catalog = api.get('Property')
        prop_name_map = {p.get('id'): p.get('name') for p in properties_catalog if p.get('id') and p.get('name')}
        
        # Normalize devices (extract custom properties)
        devices = []
        for d in devices_raw:
            device_normalized = {
                'Id': d.get('id'),
                'Name': d.get('name'),
                'SerialNumber': d.get('serialNumber'),
                'VIN': d.get('vehicleIdentificationNumber'),
                'LicensePlate': d.get('licensePlate'),
                'StateOrProvince': d.get('state'),
                'AssetType': d.get('deviceType'),
                'TimeZone': d.get('timeZoneId'),
            }
            
            # Extract custom properties
            custom_props = d.get('customProperties', [])
            for cp in custom_props:
                prop_id = cp.get('property', {}).get('id')
                prop_name = prop_name_map.get(prop_id, '')
                prop_value = cp.get('value')
                
                # Map to standard fields
                if prop_name == 'Enable Equipment Booking':
                    device_normalized['Bookable'] = str(prop_value).lower() in ['true', '1', 'on', 'yes']
                elif prop_name == 'Allow Recurring Bookings':
                    device_normalized['RecurringAllowed'] = str(prop_value).lower() in ['true', '1', 'on', 'yes']
                elif prop_name == 'Booking Approvers':
                    device_normalized['Approvers'] = prop_value.split(',') if isinstance(prop_value, str) else []
                elif prop_name == 'Fleet Managers':
                    device_normalized['FleetManagers'] = prop_value.split(',') if isinstance(prop_value, str) else []
                elif prop_name == 'Allow Double Booking':
                    device_normalized['AllowConflicts'] = str(prop_value).lower() in ['true', '1', 'on', 'yes']
                elif prop_name == 'Booking Window (Days)':
                    device_normalized['BookingWindowInDays'] = int(prop_value) if prop_value else 90
                elif prop_name == 'Maximum Booking Duration (Hours)':
                    device_normalized['MaximumDurationInMinutes'] = int(prop_value) * 60 if prop_value else 1440
                elif prop_name == 'Mailbox Language':
                    device_normalized['MailboxLanguage'] = prop_value or 'en-AU'
            
            # Defaults for missing values
            device_normalized.setdefault('Bookable', False)
            device_normalized.setdefault('BookingWindowInDays', 90)
            device_normalized.setdefault('MaximumDurationInMinutes', 1440)
            device_normalized.setdefault('MailboxLanguage', 'en-AU')
            
            devices.append(device_normalized)
        
        # Limit devices for testing
        if max_devices > 0:
            devices = devices[:max_devices]
        
        logging.info(f'Processing {len(devices)} device(s)')
        
        # Get tenant ID from OAuth callback (stored when user connected Exchange)
        client_id = api_key if api_key else database
        try:
            tenant_id_secret = key_vault_client.get_secret(f"client-{client_id}-exchange-tenant-id")
            tenant_id = tenant_id_secret.value
        except Exception as e:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Exchange not connected. Please click 'Connect to Exchange' in the Add-In first.",
                    "details": str(e)
                }),
                status_code=401,
                mimetype="application/json"
            )
        
        # Get application token using certificate (APPLICATION permissions, not delegated)
        try:
            access_token = get_application_graph_token(api_key, tenant_id)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Failed to authenticate with Microsoft Graph",
                    "details": str(e)
                }),
                status_code=500,
                mimetype="application/json"
            )
        
        # Get PowerShell credentials for Exchange cmdlets
        app_id = ENTRA_CLIENT_ID  # Same app ID used for Graph authentication
        key_vault_url = KEY_VAULT_URL  # Key Vault URL for certificate retrieval
        try:
            if key_vault_client and app_id and key_vault_url:
                logging.info(f"PowerShell credentials prepared: AppId={app_id[:8] if app_id else 'None'}..., KeyVault={key_vault_url}")
            else:
                logging.warning("PowerShell credentials not available - missing app_id or key_vault_url")
                app_id = None
                key_vault_url = None
        except Exception as e:
            logging.warning(f"PowerShell credentials setup failed: {e}")
            app_id = None
            key_vault_url = None
        
        # Get Graph client with application token
        graph_client = await get_delegated_graph_client(access_token)
        
        # Process each device
        results = []
        for device in devices:
            if not device.get('SerialNumber'):
                continue
            
            result = await update_equipment_mailbox(
                graph_client, 
                device, 
                equipment_domain, 
                access_token,
                app_id=app_id,
                key_vault_url=key_vault_url
            )
            results.append({
                'device': device.get('Name'),
                'serialNumber': device.get('SerialNumber'),
                **result
            })
        
        # Summary
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        
        # Log usage
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_usage(database, 'sync-to-exchange', True, execution_time)
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "processed": len(results),
                "successful": successful,
                "failed": failed,
                "results": results,
                "executionTimeMs": execution_time
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f'Error in sync-to-exchange: {str(e)}', exc_info=True)
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        if 'database' in locals():
            log_usage(database, 'sync-to-exchange', False, execution_time)
        
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
