#!/usr/bin/env python3
"""
Setup Custom Properties for FleetBridge
Creates all required custom properties in MyGeotab if they don't exist.
"""

import sys
from mygeotab import API

# Property definitions
PROPERTIES = [
    {
        'name': 'Enable Equipment Booking',
        'description': 'Enable this device for equipment booking in Exchange',
        'type': 'Boolean'
    },
    {
        'name': 'Allow Recurring Bookings',
        'description': 'Allow recurring bookings for this equipment',
        'type': 'Boolean'
    },
    {
        'name': 'Booking Approvers',
        'description': 'Email addresses of booking approvers (comma-separated)',
        'type': 'String'
    },
    {
        'name': 'Fleet Managers',
        'description': 'Email addresses of fleet managers (comma-separated)',
        'type': 'String'
    },
    {
        'name': 'Allow Double Booking',
        'description': 'Allow multiple bookings at the same time',
        'type': 'Boolean'
    },
    {
        'name': 'Booking Window (Days)',
        'description': 'Number of days in advance bookings can be made',
        'type': 'Number'
    },
    {
        'name': 'Maximum Booking Duration (Hours)',
        'description': 'Maximum duration for a single booking in hours',
        'type': 'Number'
    },
    {
        'name': 'Mailbox Language',
        'description': 'Language code for the equipment mailbox (e.g., en-AU, en-US)',
        'type': 'String'
    }
]

def setup_properties(database, username, password):
    """Create custom properties in MyGeotab."""
    print(f"Connecting to MyGeotab database: {database}")
    api = API(username=username, password=password, database=database)
    api.authenticate()
    print("✓ Connected successfully\n")
    
    # Get existing properties
    print("Fetching existing properties...")
    existing_properties = api.get('Property')
    existing_names = {prop['name'] for prop in existing_properties}
    print(f"✓ Found {len(existing_properties)} existing properties\n")
    
    # Get the Device property set
    print("Fetching property sets...")
    property_sets = api.get('PropertySet')
    device_set = next((ps for ps in property_sets if ps['name'] == 'Device'), None)
    
    if not device_set:
        print("✗ Error: Device property set not found")
        return False
    
    print(f"✓ Found Device property set: {device_set['id']}\n")
    
    # Create missing properties
    created_count = 0
    skipped_count = 0
    
    for prop_def in PROPERTIES:
        prop_name = prop_def['name']
        
        if prop_name in existing_names:
            print(f"⊘ Skipping '{prop_name}' (already exists)")
            skipped_count += 1
            continue
        
        print(f"+ Creating property: {prop_name}")
        print(f"  Description: {prop_def['description']}")
        print(f"  Type: {prop_def['type']}")
        
        # Create the property
        new_property = {
            'name': prop_name,
            'description': prop_def['description'],
            'propertySet': {'id': device_set['id']},
            'isSystem': False
        }
        
        try:
            result = api.add('Property', new_property)
            print(f"  ✓ Created with ID: {result}\n")
            created_count += 1
        except Exception as e:
            print(f"  ✗ Error creating property: {e}\n")
            return False
    
    print("\n" + "="*60)
    print(f"Setup complete!")
    print(f"  Created: {created_count} properties")
    print(f"  Skipped: {skipped_count} properties (already existed)")
    print("="*60)
    
    return True

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python setup-properties.py <database> <username> <password>")
        print("\nExample:")
        print("  python setup-properties.py goac admin@example.com mypassword")
        sys.exit(1)
    
    database = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    success = setup_properties(database, username, password)
    sys.exit(0 if success else 1)

