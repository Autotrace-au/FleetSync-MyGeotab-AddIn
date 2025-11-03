import azure.functions as func
import logging
import json
import os
from mygeotab import API
from azure.keyvault.secrets import SecretClient
from azure.keyvault.certificates import CertificateClient
from azure.identity import DefaultAzureCredential, CertificateCredential
from datetime import datetime
import msal
from msgraph import GraphServiceClient
from msgraph.generated.users.item.mailbox_settings.mailbox_settings_request_builder import MailboxSettingsRequestBuilder
import base64
import tempfile
import asyncio

app = func.FunctionApp()

# Test route to verify loading
@app.route(route="test1", auth_level=func.AuthLevel.ANONYMOUS)
def test1(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("Test 1 works", status_code=200)

# Configuration
KEY_VAULT_URL = os.environ.get('KEY_VAULT_URL', '')  # e.g., https://fleetbridge-vault.vault.azure.net/
USE_KEY_VAULT = os.environ.get('USE_KEY_VAULT', 'false').lower() == 'true'

# Multi-tenant OAuth configuration
ENTRA_CLIENT_ID = os.environ.get('ENTRA_CLIENT_ID')
ENTRA_CLIENT_SECRET_NAME = os.environ.get('ENTRA_CLIENT_SECRET_NAME', 'EntraAppClientSecret')
ENTRA_AUTHORITY = "https://login.microsoftonline.com/organizations"
ENTRA_SCOPES = [
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/MailboxSettings.ReadWrite",
    "https://graph.microsoft.com/User.ReadWrite.All"
    # Note: offline_access is reserved and automatically included by Azure AD
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
        client_id = req.params.get('clientId')
        if not client_id:
            return func.HttpResponse("Missing clientId parameter", status_code=400)
        
        # Generate random state to prevent CSRF
        import secrets
        state = secrets.token_urlsafe(32)
        
        # Encode client_id in state (in production, use Redis/Table Storage)
        state_with_client = f"{state}:{client_id}"
        
        # Build authorization URL
        redirect_uri = f"https://{os.environ.get('WEBSITE_HOSTNAME', 'localhost:7071')}/api/authcallback"
        
        from urllib.parse import urlencode
        auth_params = {
            'client_id': ENTRA_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'response_mode': 'query',
            'scope': ' '.join(ENTRA_SCOPES),
            'state': state_with_client,
            'prompt': 'consent'  # Force consent screen
        }
        
        auth_url = f"{ENTRA_AUTHORITY}/oauth2/v2.0/authorize?{urlencode(auth_params)}"
        
        logging.info(f"OAuth login initiated for client: {client_id}")
        
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
        
        # Get authorization code and state
        code = req.params.get('code')
        state = req.params.get('state')
        
        if not code or not state:
            return func.HttpResponse("Missing code or state parameter", status_code=400)
        
        # Extract client_id from state
        try:
            state_nonce, client_id = state.split(':', 1)
        except:
            return func.HttpResponse("Invalid state parameter", status_code=400)
        
        # Exchange code for tokens
        client_secret = get_client_secret()
        redirect_uri = f"https://{os.environ.get('WEBSITE_HOSTNAME')}/api/authcallback"
        
        msal_app = msal.ConfidentialClientApplication(
            ENTRA_CLIENT_ID,
            authority=ENTRA_AUTHORITY,
            client_credential=client_secret
        )
        
        result = msal_app.acquire_token_by_authorization_code(
            code,
            scopes=ENTRA_SCOPES,
            redirect_uri=redirect_uri
        )
        
        if "error" in result:
            logging.error(f"Token acquisition error: {result.get('error_description')}")
            raise ValueError(result.get('error_description', 'Failed to acquire token'))
        
        # Extract tokens
        access_token = result.get('access_token')
        refresh_token = result.get('refresh_token')
        id_token_claims = result.get('id_token_claims', {})
        tenant_id = id_token_claims.get('tid')
        user_email = id_token_claims.get('preferred_username')
        
        if not refresh_token:
            raise ValueError("No refresh token received (offline_access scope missing?)")
        
        logging.info(f"OAuth tokens received for client: {client_id}, tenant: {tenant_id}")
        
        # Store refresh token in Key Vault
        if key_vault_client:
            secret_name = f"client-{client_id}-exchange-refresh-token"
            key_vault_client.set_secret(secret_name, refresh_token)
            
            # Also store tenant ID (needed for token refresh)
            tenant_secret_name = f"client-{client_id}-exchange-tenant-id"
            key_vault_client.set_secret(tenant_secret_name, tenant_id)
            
            # Store user email for display
            email_secret_name = f"client-{client_id}-exchange-user-email"
            key_vault_client.set_secret(email_secret_name, user_email)
            
            logging.info(f"Stored tokens for client {client_id} in Key Vault")
        
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
                    <h1>✅ Successfully Connected to Exchange!</h1>
                    <p>FleetBridge can now sync your MyGeotab devices with Exchange Online.</p>
                    
                    <div class="info">
                        <p><strong>Connected as:</strong> {user_email}</p>
                        <p><strong>Organization ID:</strong> {tenant_id}</p>
                    </div>
                    
                    <p>You can now close this window and return to the MyGeotab Add-In.</p>
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
        req_body = req.get_json()
        client_id = req_body.get('clientId')
        
        if not client_id:
            return func.HttpResponse(
                json.dumps({"connected": False, "error": "Missing clientId"}),
                status_code=400,
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
        # Parse request body
        req_body = req.get_json()
        
        # Get credentials (either from Key Vault or request)
        api_key = req_body.get('apiKey')
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


async def update_equipment_mailbox(graph_client, device, equipment_domain):
    """
    Update an equipment mailbox based on MyGeotab device data.
    Does NOT create mailboxes - only updates existing ones.
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
        # Update display name
        if display_name:
            await graph_client.users.by_user_id(mailbox.id).patch({
                'displayName': display_name
            })
        
        # Update mailbox regional settings (timezone, language)
        timezone = convert_to_windows_timezone(device.get('TimeZone'))
        language = device.get('MailboxLanguage', 'en-AU')
        
        await graph_client.users.by_user_id(mailbox.id).mailbox_settings.patch({
            'timeZone': timezone,
            'language': {'locale': language}
        })
        
        # Update calendar settings
        bookable = device.get('Bookable', False)
        
        if not bookable:
            # Disable booking
            logging.info(f"Bookable=False: Disabling booking for {primary_smtp}")
            # Note: Calendar processing settings are managed via Exchange cmdlets
            # Graph API has limited calendar processing capabilities
            # This would require Exchange Online PowerShell or direct REST calls
        else:
            logging.info(f"Bookable=True: Booking enabled for {primary_smtp}")
            # Apply booking rules via Exchange REST API or PowerShell
        
        # Update user properties (State/Province for directory)
        state = device.get('StateOrProvince')
        if state:
            await graph_client.users.by_user_id(mailbox.id).patch({
                'state': state
            })
        
        logging.info(f"Successfully updated mailbox: {primary_smtp}")
        return {'success': True, 'email': primary_smtp, 'displayName': display_name}
        
    except Exception as e:
        logging.error(f"Error updating mailbox {primary_smtp}: {e}")
        return {'success': False, 'reason': 'update_failed', 'error': str(e), 'email': primary_smtp}


@app.route(route="sync-to-exchange", auth_level=func.AuthLevel.ANONYMOUS)
async def sync_to_exchange(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sync MyGeotab devices to Exchange Online equipment mailboxes.
    
    Request body:
    {
        "apiKey": "client-api-key",  // OR provide credentials directly
        "database": "mygeotab_db",
        "username": "user@example.com",
        "password": "password",
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
        # Parse request body
        req_body = req.get_json()
        
        # Get MyGeotab credentials
        api_key = req_body.get('apiKey')
        database = req_body.get('database')
        username = req_body.get('username')
        password = req_body.get('password')
        max_devices = req_body.get('maxDevices', 0)
        
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
        equipment_domain = os.environ.get('EQUIPMENT_DOMAIN')
        
        if not equipment_domain:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "EQUIPMENT_DOMAIN not configured in function app settings"
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
        
        # Check if client has connected Exchange (get delegated token)
        client_id = api_key if api_key else database
        try:
            access_token = get_delegated_graph_token(client_id)
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
        
        # Get Graph client with delegated token
        graph_client = await get_delegated_graph_client(access_token)
        
        # Process each device
        results = []
        for device in devices:
            if not device.get('SerialNumber'):
                continue
            
            result = await update_equipment_mailbox(graph_client, device, equipment_domain)
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
