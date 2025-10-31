import azure.functions as func
import logging
import json
import os
from mygeotab import API
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from datetime import datetime

app = func.FunctionApp()

# Configuration
KEY_VAULT_URL = os.environ.get('KEY_VAULT_URL', '')  # e.g., https://fleetbridge-vault.vault.azure.net/
USE_KEY_VAULT = os.environ.get('USE_KEY_VAULT', 'false').lower() == 'true'

# Initialize Key Vault client if enabled
key_vault_client = None
if USE_KEY_VAULT and KEY_VAULT_URL:
    try:
        credential = DefaultAzureCredential()
        key_vault_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
        logging.info('Key Vault client initialized')
    except Exception as e:
        logging.error(f'Failed to initialize Key Vault client: {e}')

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

@app.route(route="update-device-properties", auth_level=func.AuthLevel.FUNCTION)
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

