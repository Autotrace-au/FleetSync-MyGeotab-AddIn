import azure.functions as func
import logging
import json
import os
import subprocess
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# Diagnostic endpoint to test PowerShell integration
@app.route(route="test-powershell", auth_level=func.AuthLevel.ANONYMOUS)
def test_powershell(req: func.HttpRequest) -> func.HttpResponse:
    """Test PowerShell Core and Exchange Online module availability"""
    
    results = {}
    
    try:
        # Test 1: Check if PowerShell Core is available
        logging.info("Testing PowerShell Core availability...")
        ps_result = subprocess.run(['pwsh', '--version'], 
                                 capture_output=True, text=True, timeout=30)
        
        results['powershell_core'] = {
            'available': ps_result.returncode == 0,
            'version': ps_result.stdout.strip() if ps_result.returncode == 0 else ps_result.stderr.strip(),
            'returncode': ps_result.returncode
        }
        
        # Test 2: Check Exchange Online module
        logging.info("Testing Exchange Online PowerShell module...")
        module_test = subprocess.run([
            'pwsh', '-c', 'Import-Module ExchangeOnlineManagement -Force; Get-Module ExchangeOnlineManagement'
        ], capture_output=True, text=True, timeout=30)
        
        results['exchange_module'] = {
            'available': 'ExchangeOnlineManagement' in module_test.stdout,
            'output': module_test.stdout.strip(),
            'error': module_test.stderr.strip(),
            'returncode': module_test.returncode
        }
        
        # Test 3: Check Key Vault access
        logging.info("Testing Key Vault access...")
        try:
            key_vault_url = os.environ.get('KEY_VAULT_URL')
            if key_vault_url:
                credential = DefaultAzureCredential()
                client = SecretClient(vault_url=key_vault_url, credential=credential)
                
                # Try to access the certificate secret
                cert_secret = client.get_secret('powershell-cert-data')
                
                results['key_vault'] = {
                    'accessible': True,
                    'certificate_found': len(cert_secret.value) > 0,
                    'certificate_length': len(cert_secret.value)
                }
            else:
                results['key_vault'] = {
                    'accessible': False,
                    'error': 'KEY_VAULT_URL not configured'
                }
        except Exception as kv_error:
            results['key_vault'] = {
                'accessible': False,
                'error': str(kv_error)
            }
        
        # Test 4: Check environment variables
        results['environment'] = {
            'ENTRA_CLIENT_ID': bool(os.environ.get('ENTRA_CLIENT_ID')),
            'KEY_VAULT_URL': bool(os.environ.get('KEY_VAULT_URL')),
            'USE_KEY_VAULT': os.environ.get('USE_KEY_VAULT', 'false')
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