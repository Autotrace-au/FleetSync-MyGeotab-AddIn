# FleetSync MyGeotab Property Update Function

Azure Function to update MyGeotab device custom properties using the Python SDK.

## Why This Function?

The MyGeotab JavaScript SDK has issues updating custom properties (JsonSerializerException errors). This Azure Function uses the Python SDK which works reliably.

## Deployment

### Prerequisites

1. Azure CLI installed: `brew install azure-cli`
2. Azure Functions Core Tools: `brew install azure-functions-core-tools@4`
3. Python 3.9 or higher

### Deploy to Azure

1. **Login to Azure:**
   ```bash
   az login
   ```

2. **Create a resource group (if needed):**
   ```bash
   az group create --name FleetSyncRG --location australiaeast
   ```

3. **Create a storage account:**
   ```bash
   az storage account create \
     --name fleetsyncstore \
     --resource-group FleetSyncRG \
     --location australiaeast \
     --sku Standard_LRS
   ```

4. **Create the Function App:**
   ```bash
   az functionapp create \
     --resource-group FleetSyncRG \
     --consumption-plan-location australiaeast \
     --runtime python \
     --runtime-version 3.11 \
     --functions-version 4 \
     --name fleetsync-mygeotab \
     --storage-account fleetsyncstore \
     --os-type Linux
   ```

5. **Deploy the function:**
   ```bash
   cd azure-function
   func azure functionapp publish fleetsync-mygeotab
   ```

6. **Get the function URL and key:**
   ```bash
   az functionapp function show \
     --resource-group FleetSyncRG \
     --name fleetsync-mygeotab \
     --function-name update-device-properties
   
   az functionapp keys list \
     --resource-group FleetSyncRG \
     --name fleetsync-mygeotab
   ```

## Local Testing

1. **Create a virtual environment:**
   ```bash
   cd azure-function
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run locally:**
   ```bash
   func start
   ```

4. **Test with curl:**
   ```bash
   curl -X POST http://localhost:7071/api/update-device-properties \
     -H "Content-Type: application/json" \
     -d '{
       "database": "your_database",
       "username": "your_username",
       "password": "your_password",
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
     }'
   ```

## API Endpoint

**URL:** `https://fleetsync-mygeotab.azurewebsites.net/api/update-device-properties?code=YOUR_FUNCTION_KEY`

**Method:** POST

**Request Body:**
```json
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
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Device 2018 Mazda 3 updated successfully"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Error message"
}
```

## Security Considerations

1. **Function Key:** The function requires a function key for authentication
2. **HTTPS Only:** All requests must use HTTPS
3. **CORS:** Configure CORS in Azure to only allow requests from MyGeotab domains
4. **Credentials:** MyGeotab credentials are passed in the request (consider using Azure Key Vault for production)

## Cost

Azure Functions Consumption Plan:
- First 1 million executions per month: FREE
- After that: $0.20 per million executions
- Very cost-effective for this use case

