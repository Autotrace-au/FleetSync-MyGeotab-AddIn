# MyGeotab Add-In

This folder contains the MyGeotab Add-In files that are loaded into the MyGeotab system.

## Files

- **`index.html`** - The main Add-In interface that users see in MyGeotab
- **`styles.css`** - CSS styles for the Add-In interface  
- **`configuration.json`** - MyGeotab Add-In manifest file that defines the Add-In
- **`images/`** - Icons and images used by the Add-In
- **`translations/`** - Language files for internationalization

## How it works

1. The `configuration.json` file is hosted on GitHub and referenced by MyGeotab
2. MyGeotab loads the `index.html` file specified in the configuration
3. The Add-In provides a user interface for syncing MyGeotab devices to Exchange equipment mailboxes
4. It communicates with the Azure Functions backend to perform the actual sync operations

## Development

To make changes to the Add-In:

1. Edit the files in this folder
2. Test locally by opening `index.html` in a browser (limited functionality without MyGeotab API)
3. Commit changes to git
4. Update the commit hash in `configuration.json` to point to the new version
5. Test in MyGeotab using the updated configuration URL

## CDN URLs

The Add-In is served directly from GitHub:
- Configuration: `https://raw.githubusercontent.com/Autotrace-au/FleetBridge-MyGeotab-AddIn/main/mygeotab-addin/configuration.json`
- Add-In HTML: Referenced in the configuration file with specific commit hash for version control