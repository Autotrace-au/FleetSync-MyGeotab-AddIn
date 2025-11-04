import os
import logging
import json
import requests
from azure.functions import HttpRequest, HttpResponse
from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

# Container App URL
CONTAINER_APP_URL = "https://exchange-calendar-processor.mangosmoke-ee55f1a9.australiaeast.azurecontainerapps.io"

# Configuration
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")
ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID") 
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID")

def main(req: HttpRequest) -> HttpResponse:
    """Process calendar sync request using Container App."""
    
    try:
        # Parse request body
        req_body = req.get_json()
        if not req_body:
            return HttpResponse(
                json.dumps({"error": "Request body required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        api_key = req_body.get('apiKey')
        if not api_key:
            return HttpResponse(
                json.dumps({"error": "API key required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Get certificate data from Key Vault
        try:
            credential = ManagedIdentityCredential()
            secret_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
            certificate_data = secret_client.get_secret("powershell-cert-data").value
        except Exception as e:
            logging.error(f"Failed to get certificate from Key Vault: {str(e)}")
            return HttpResponse(
                json.dumps({"error": "Certificate access failed"}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Prepare Container App request
        container_request = {
            "mailboxEmail": f"test@equipment.garageofawesome.com.au",
            "deviceName": "Test Device", 
            "tenantId": ENTRA_TENANT_ID,
            "clientId": ENTRA_CLIENT_ID,
            "certificateData": certificate_data
        }
        
        # Call Container App
        try:
            response = requests.post(
                f"{CONTAINER_APP_URL}/process-mailbox",
                json=container_request,
                timeout=30
            )
            
            return HttpResponse(
                response.text,
                status_code=response.status_code,
                mimetype="application/json"
            )
        
        except requests.exceptions.RequestException as e:
            logging.error(f"Container App request failed: {str(e)}")
            return HttpResponse(
                json.dumps({"error": "Container App request failed"}),
                status_code=500,
                mimetype="application/json"
            )
            
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json"
        )