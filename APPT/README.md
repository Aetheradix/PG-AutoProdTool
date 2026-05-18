# Auto Production Planner - IIS Deployment Guide

This document outlines the steps required to deploy the Auto Production Planner (FastAPI + React SPA) on a Windows Server running IIS.

## System Prerequisites
1. **Python 3.11+**: Installed system-wide (ensure "Add Python to environment variables" is checked during installation).
2. **IIS (Internet Information Services)**: Installed and running.
3. **Microsoft HttpPlatformHandler v1.2**: Must be installed on the IIS server to proxy requests to the Python process. (Download from Microsoft's official site).
4. **ODBC Driver 17 for SQL Server**: Required for the Python application to communicate with the MS SQL database.

---

## Deployment Steps

### 1. Extract Application Files
Extract the provided ZIP file to your preferred IIS hosting directory. 
*Recommended: `C:\inetpub\wwwroot\AutoProdPlanner`*

### 2. Prepare the Python Virtual Environment
Open Command Prompt as **Administrator**, navigate to the extracted folder, and run the following commands to isolate the application dependencies:

```cmd
cd C:\inetpub\wwwroot\AutoProdPlanner
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt


###3. Create Required Folders
Ensure the following folders exist in the root directory (create them if they do not):

logs (For IIS HttpPlatformHandler stdout logging)

###4. Configure web.config
Open the web.config file located in the root directory.
You must update the processPath attribute to point to the exact location of the python.exe inside the newly created virtual environment.

Example:
processPath="C:\inetpub\wwwroot\AutoProdPlanner\.venv\Scripts\python.exe"

###5. Set Folder Permissions (CRITICAL)
The application requires read/write access to manage its environment variables, write logs, and manage Excel input/output templates.

Right-click the root folder (AutoProdPlanner) -> Properties -> Security.

Edit permissions and add the IIS AppPool identity that will be running the site (usually IIS AppPool\DefaultAppPool).

Grant this identity Modify (Read & Write) permissions.

###6. Configure Environment Variables
Ensure the .env file in the root directory contains the correct MS SQL Server credentials.

If the database password contains special characters, it must be wrapped in double quotes (e.g., DB_PASSWORD="MyP@ssw0rd!").

Verify the port (Default MS SQL port is 1433).

###7. Add Site to IIS
Open IIS Manager.

Add a new Website (or Application under Default Web Site).

Set the Physical Path to the extracted root folder.

Start the Application Pool and Website.