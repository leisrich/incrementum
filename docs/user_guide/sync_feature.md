# Cloud Synchronization

Incrementum allows you to synchronize your knowledge collection across multiple devices using various cloud services. This feature ensures that your learning materials, review progress, and spaced repetition data are available everywhere you work.

## Table of Contents

1. [Overview](#overview)
2. [Supported Sync Providers](#supported-sync-providers)
3. [Setting Up Synchronization](#setting-up-synchronization)
4. [Syncing Your Collection](#syncing-your-collection)
5. [Sync History](#sync-history)
6. [Troubleshooting](#troubleshooting)

## Overview

The sync feature allows you to:

- Back up your entire knowledge collection to cloud storage
- Restore from cloud backups when needed
- Keep multiple installations of Incrementum in sync across different devices
- Access your learning materials from anywhere

The sync process:

1. Creates a backup of your database and document files
2. Uploads this backup to your configured cloud provider
3. Checks for newer backups on the cloud provider
4. Automatically restores from newer backups when found

All synchronization operations happen in the background, allowing you to continue working with Incrementum while syncing.

## Supported Sync Providers

Incrementum supports the following sync providers:

### GitHub

Store your knowledge collection in a private GitHub repository. This option is excellent for users who are already familiar with GitHub and want version control for their knowledge collection.

**Requirements:**
- GitHub account
- Personal Access Token with 'repo' scope
- Repository for storing backups

### Google Drive

Sync your collection with Google Drive for seamless integration with the Google ecosystem.

**Requirements:**
- Google account
- OAuth credentials from Google Cloud Console
- Folder ID for storing backups

### Dropbox

Use Dropbox to store your knowledge collection and sync across devices.

**Requirements:**
- Dropbox account
- API access token
- Folder path for storing backups

### Local Folder

For users who prefer to handle synchronization manually or use a third-party sync service like OneDrive, Syncthing, or a network drive.

**Requirements:**
- Local folder path (can be in a folder that's synced by another service)

## Setting Up Synchronization

To set up synchronization:

1. Open Incrementum
2. Go to **File → Sync → Configure Sync Settings**
3. Select a sync provider from the grid of available options
4. Click the **Configure** button for your chosen provider
5. Enter the required credentials and settings
6. Click **Save** to store your configuration

### GitHub Setup

1. Create a Personal Access Token on GitHub:
   - Go to GitHub → Settings → Developer settings → Personal access tokens
   - Generate a new token with 'repo' scope
   - Copy the token

2. In Incrementum:
   - Configure GitHub sync with your token
   - Specify repository (format: username/repo)
   - Set branch (default: main)

### Google Drive Setup

1. Create a Google Cloud project:
   - Go to the Google Cloud Console (console.cloud.google.com)
   - Create a new project
   - Enable the Google Drive API
   - Create OAuth credentials (download as JSON)

2. In Incrementum:
   - Select your credentials file
   - Enter the folder ID for storing backups
   
### Dropbox Setup

1. Create a Dropbox app:
   - Go to Dropbox Developer Console (developers.dropbox.com)
   - Create a new app with the following permissions:
     - files.content.read
     - files.content.write
   - Generate an access token

2. In Incrementum:
   - Enter your access token
   - Specify a folder path (default: /Incrementum)

### Local Folder Setup

1. In Incrementum:
   - Click "Select Folder"
   - Choose a local directory for storing backups
   - This can be a folder that's synced by another service (OneDrive, etc.)

## Syncing Your Collection

Once you've configured a sync provider, you can sync your knowledge collection:

1. Go to **File → Sync → Sync with Cloud**
2. Alternatively, click the **Sync** button on the Cloud Sync page
3. Confirm the synchronization when prompted

The sync process involves:

1. **Backing up your collection**: Incrementum creates a complete backup of your database and document files.
2. **Uploading to the cloud**: The backup is uploaded to your configured provider.
3. **Checking for updates**: Incrementum checks if there's a newer backup in the cloud.
4. **Synchronizing data**: If a newer backup is found, Incrementum will restore from it automatically.

The entire process runs in the background, with a progress dialog showing the current status.

## Sync History

You can view the history of sync operations on the Cloud Sync page:

1. Go to **File → Sync → Sync with Cloud**
2. Scroll down to the Sync History section

The history shows:
- Provider name
- Last sync date and time
- Sync status (Success/Failed)
- Additional messages about the sync operation

This history helps you track when your collection was last synced and identify any issues that may have occurred.

## Automatic Sync

For critical work, consider setting up a regular sync schedule:

1. Sync at the beginning of each study session
2. Sync after making significant additions to your collection
3. Sync before closing Incrementum

## Troubleshooting

### Sync Fails to Connect

**Problem**: Incrementum can't connect to your cloud provider.

**Solutions**:
- Check your internet connection
- Verify that your credentials are still valid (tokens may expire)
- Check if the service is experiencing downtime

### Sync Conflicts

**Problem**: Changes were made on multiple devices, creating conflicting versions.

**Solution**: Incrementum uses a "newest wins" strategy. The backup with the most recent timestamp is considered authoritative. If you need to recover data from an older backup:

1. Go to your cloud storage directly
2. Download the specific backup you want to restore
3. Use **File → Backup & Restore → Restore Backup** to manually restore from that file

### Invalid Credentials

**Problem**: Your cloud provider credentials are invalid or expired.

**Solution**:
1. Go to **File → Sync → Configure Sync Settings**
2. Reconfigure your sync provider with updated credentials

### Local Folder Not Found

**Problem**: The configured local folder for sync does not exist.

**Solution**:
1. Go to **File → Sync → Configure Sync Settings**
2. Select the Local Folder provider
3. Choose a valid folder path

## Best Practices

To make the most of the sync feature:

1. **Sync regularly**: Sync before and after significant work sessions
2. **Verify successful syncs**: Always check that sync operations complete successfully
3. **Keep backups**: Periodically export manual backups as an additional safety measure
4. **Use secure credentials**: Use strong tokens and keep them secure
5. **Only sync with trusted devices**: Only install Incrementum on devices you trust

---
