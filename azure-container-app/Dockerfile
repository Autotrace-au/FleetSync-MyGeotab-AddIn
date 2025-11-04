# Use PowerShell 7 on Ubuntu base image
FROM mcr.microsoft.com/powershell:7.4-ubuntu-22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Exchange Online Management module
RUN pwsh -Command "Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber -Scope AllUsers"

# Create app directory
WORKDIR /app

# Copy PowerShell scripts
COPY exchange-processor.ps1 .
COPY start-server.ps1 .

# Make scripts executable
RUN chmod +x *.ps1

# Expose port
EXPOSE 8080

# Start the PowerShell HTTP server
CMD ["pwsh", "./start-server.ps1"]