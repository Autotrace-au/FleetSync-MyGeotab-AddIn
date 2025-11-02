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
        # Get credentials from Key Vault using API key
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
        # Fallback: Get credentials from request parameters (for testing or migration)
        if database and username and password:
            return (database, username, password)
        return None

def log_usage(database, operation, success, execution_time_ms, api_key=None):
    """
    Log usage for billing and monitoring.
    """
    usage_log = {
        'timestamp': datetime.utcnow().isoformat(),
        'database': database,
        'apiKey': api_key if api_key else 'direct-auth',
        'operation': operation,
        'success': success,
        'execution_time_ms': execution_time_ms
    }
    logging.info(f'USAGE: {json.dumps(usage_log)}')

@app.route(route="update-device-properties", auth_level=func.AuthLevel.FUNCTION)
def update_device_properties(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function to update MyGeotab device custom properties.

    Supports two authentication modes:

    Mode 1 - API key (recommended for production):
    {
        "apiKey": "client-api-key-here",
        "deviceId": "b1",
        "properties": {
            "bookable": true,
            "recurring": true,
            "approvers": "email@example.com",
            "fleetManagers": "",
            "conflicts": false,
            "windowDays": 3,
            "maxDurationHours": 48,
            "language": "en-AU"
        }
    }

    Mode 2 - Direct credentials (for testing/migration):
    {
        "database": "database_name",
        "username": "user@example.com",
        "password": "password",
        "deviceId": "b1",
        "properties": {...}
    }
    """
    # Handle preflight OPTIONS request
    if req.method == 'OPTIONS':
        return create_cors_response('', 200)

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
            return create_cors_response(
                json.dumps({
                    "success": False,
                    "error": "Invalid credentials or API key"
                }),
                401
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
        logging.info(f'Device object keys: {list(device.keys())}')
        logging.info(f'Device deviceType: {device.get("deviceType")}')
        logging.info(f'Device serialNumber: {device.get("serialNumber")}')
        
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
        logging.info(f'Property lookup: {json.dumps({k: v["name"] for k, v in prop_lookup.items()}, indent=2)}')
        
        # Build updated customProperties array
        # Strategy: Start with existing properties, then update/add the ones we're changing
        existing_props = device.get('customProperties', [])
        logging.info(f'Device has {len(existing_props)} existing custom properties')

        # Create a dictionary of property ID -> PropertyValue for easy lookup
        custom_props_dict = {}

        # First, add all existing properties to the dictionary
        for existing_prop in existing_props:
            prop_id = existing_prop.get('property', {}).get('id')
            if prop_id:
                custom_props_dict[prop_id] = existing_prop

        # Now update/add the properties we're changing
        for key, value in properties.items():
            if key not in prop_lookup:
                logging.warning(f'Property not found: {key}')
                continue

            prop_info = prop_lookup[key]
            prop_id = prop_info['id']

            # Convert empty strings to None
            if value == '':
                value = None
            # Convert all values to strings for MyGeotab
            # MyGeotab expects all custom property values as strings
            elif isinstance(value, bool):
                value = 'true' if value else 'false'
            elif isinstance(value, (int, float)):
                value = str(value)
            elif value is not None:
                value = str(value)

            logging.info(f'Setting property: {key} ({prop_info["name"]}) = {value}')

            # Create PropertyValue structure
            property_value = {
                'property': {'id': prop_id},
                'value': value
            }

            # Update or add to dictionary (this prevents duplicates)
            custom_props_dict[prop_id] = property_value

        # Convert dictionary back to list
        custom_properties = list(custom_props_dict.values())

        logging.info(f'Final custom_properties array has {len(custom_properties)} items')

        # IMPORTANT: Update the device object in-place, then call set() with the full device
        # This is the pattern used by autotrace-fields that works correctly
        device['customProperties'] = custom_properties

        # Call Set to update the device with the full device object
        logging.info('Calling Set to update device')
        logging.info(f'Custom properties count: {len(custom_properties)}')

        try:
            result = api.set('Device', device)
            logging.info(f'Set result: {result}')
        except Exception as set_error:
            logging.error(f'Set call failed: {str(set_error)}')
            logging.error(f'Set call error type: {type(set_error).__name__}')
            raise

        logging.info('Device updated successfully')

        # Log usage for billing
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_usage(database, 'update-device-properties', True, execution_time, api_key)

        return create_cors_response(
            json.dumps({
                "success": True,
                "message": f"Device {device.get('name')} updated successfully",
                "database": database,
                "deviceId": device_id
            }),
            200
        )

    except Exception as e:
        logging.error(f'Error updating device: {str(e)}', exc_info=True)

        # Log failed usage
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        if 'database' in locals():
            log_usage(database, 'update-device-properties', False, execution_time, api_key if 'api_key' in locals() else None)

        return create_cors_response(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            500
        )

def create_cors_response(body, status_code=200):
    """
    Create HTTP response with CORS headers for MyGeotab domains.
    """
    return func.HttpResponse(
        body,
        status_code=status_code,
        mimetype="application/json",
        headers={
            'Access-Control-Allow-Origin': '*',  # Allow all origins (Azure CORS will filter)
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
    )

@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint for monitoring.
    """
    # Handle preflight OPTIONS request
    if req.method == 'OPTIONS':
        return create_cors_response('', 200)

    return create_cors_response(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "keyVaultEnabled": USE_KEY_VAULT
        }),
        200
    )

