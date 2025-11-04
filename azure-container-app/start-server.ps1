# PowerShell HTTP Server for Exchange Calendar Processing
# This creates a simple HTTP server that processes Exchange calendar requests

$port = 8080
# PowerShell HTTP Server for Exchange Calendar Processing
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add('http://+:8080/')
$listener.Start()

Write-Host "Exchange Calendar Processor listening on port 8080..."

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        
        # Add comprehensive CORS headers
        $response.Headers.Add("Access-Control-Allow-Origin", "*")
        $response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        $response.Headers.Add("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, Accept, Origin")
        $response.Headers.Add("Access-Control-Max-Age", "3600")
        
        $path = $request.Url.AbsolutePath
        $method = $request.HttpMethod
        
        Write-Host "Request: $method $path"
        
        if ($method -eq "OPTIONS") {
            # Handle preflight requests
            $response.StatusCode = 200
            $response.Close()
            continue
        }
        
        if ($path -eq "/health" -and $method -eq "GET") {
            # Health check endpoint
            $healthResponse = @{
                timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                status = "healthy"
                service = "exchange-calendar-processor"
            } | ConvertTo-Json
            
            $response.StatusCode = 200
            $response.ContentType = "application/json"
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($healthResponse)
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
        }
        elseif ($path -eq "/process-mailbox" -and $method -eq "POST") {
            # Calendar processing endpoint
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $requestBody = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $requestData = $requestBody | ConvertFrom-Json
                
                # Validate required parameters
                if (-not $requestData.mailboxEmail -or -not $requestData.deviceName -or -not $requestData.tenantId -or -not $requestData.clientId) {
                    $errorResponse = @{
                        success = $false
                        timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                        error = "Missing required parameters: mailboxEmail, deviceName, tenantId, clientId"
                    } | ConvertTo-Json
                    
                    $response.StatusCode = 400
                    $response.ContentType = "application/json"
                    $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorResponse)
                    $response.OutputStream.Write($buffer, 0, $buffer.Length)
                }
                else {
                    # Call the calendar processing script
                    $result = & ./exchange-processor.ps1 -MailboxEmail $requestData.mailboxEmail -DeviceName $requestData.deviceName -TenantId $requestData.tenantId -ClientId $requestData.clientId -CertificateData $requestData.certificateData
                    
                    $response.StatusCode = 200
                    $response.ContentType = "application/json"
                    $buffer = [System.Text.Encoding]::UTF8.GetBytes($result)
                    $response.OutputStream.Write($buffer, 0, $buffer.Length)
                }
            }
            catch {
                $errorResponse = @{
                    success = $false
                    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                    error = "Error processing request: $($_.Exception.Message)"
                } | ConvertTo-Json
                
                $response.StatusCode = 500
                $response.ContentType = "application/json"
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorResponse)
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
        }
        elseif ($path -eq "/api/sync-to-exchange" -and $method -eq "POST") {
            # MyGeotab Add-in compatibility endpoint
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $requestBody = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $requestData = $requestBody | ConvertFrom-Json
                
                # Extract parameters from add-in request format (support both clientId and apiKey)
                $apiKey = if ($requestData.clientId) { $requestData.clientId } else { $requestData.apiKey }
                $maxDevices = if ($requestData.maxDevices) { $requestData.maxDevices } else { 0 }
                
                Write-Host "Sync request from add-in: apiKey=$apiKey, maxDevices=$maxDevices"
                
                # For now, return a test response that matches the add-in's expected format
                # TODO: Integrate with actual MyGeotab API and process multiple devices
                $syncResponse = @{
                    success = $true
                    processed = if ($maxDevices -gt 0) { $maxDevices } else { 1 }
                    successful = if ($maxDevices -gt 0) { $maxDevices } else { 1 }
                    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                    message = "Container App integration test successful"
                    details = @{
                        apiKey = $apiKey
                        maxDevices = $maxDevices
                        containerApp = "exchange-calendar-processor"
                    }
                } | ConvertTo-Json -Depth 3
                
                $response.StatusCode = 200
                $response.ContentType = "application/json"
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($syncResponse)
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
            catch {
                $errorResponse = @{
                    success = $false
                    processed = 0
                    successful = 0
                    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                    error = "Error processing sync request: $($_.Exception.Message)"
                } | ConvertTo-Json
                
                $response.StatusCode = 500
                $response.ContentType = "application/json"
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorResponse)
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
        }
        else {
            # 404 Not Found
            $notFoundResponse = @{
                error = "Endpoint not found"
                path = $path
                method = $method
                timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
            } | ConvertTo-Json
            
            $response.StatusCode = 404
            $response.ContentType = "application/json"
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($notFoundResponse)
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
        }
        
        $response.Close()
    }
    catch {
        Write-Host "Error handling request: $($_.Exception.Message)"
        try {
            $response.StatusCode = 500
            $response.Close()
        }
        catch {
            # Ignore errors when closing response
        }
    }
}