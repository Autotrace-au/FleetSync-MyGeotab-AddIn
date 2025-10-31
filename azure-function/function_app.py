import azure.functions as func
import logging
import json
from mygeotab import API

app = func.FunctionApp()

@app.route(route="update-device-properties", auth_level=func.AuthLevel.FUNCTION)
def update_device_properties(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function to update MyGeotab device custom properties.
    
    Expected JSON body:
    {
        "database": "database_name",
        "username": "user@example.com",
        "password": "password",
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
    """
    logging.info('Update device properties function triggered')
    
    try:
        # Parse request body
        req_body = req.get_json()
        
        # Extract parameters
        database = req_body.get('database')
        username = req_body.get('username')
        password = req_body.get('password')
        device_id = req_body.get('deviceId')
        properties = req_body.get('properties')
        
        # Validate required parameters
        if not all([database, username, password, device_id, properties]):
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Missing required parameters"
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
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "message": f"Device {device.get('name')} updated successfully"
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f'Error updating device: {str(e)}', exc_info=True)
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )

