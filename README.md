# Microsoft Graph MCP Server with Amazon Bedrock

A sleek Remote Model Context Protocol (MCP) server that wraps the Microsoft Graph API for user management operations. Supports multiple simultaneous connections and is designed to work with Amazon Bedrock.

## Features

- **Remote MCP Protocol**: Full SSE (Server-Sent Events) transport support
- **Multiple Connections**: Async architecture supporting concurrent clients
- **Microsoft Graph Integration**: Direct Azure AD user management
- **4 Core Tools**:
  - `create_user` - Create new Azure AD users
  - `read_user` - Retrieve user information
  - `update_user` - Modify existing users
  - `delete_user` - Remove users from Azure AD

## Prerequisites

- Python 3.10+
- Azure AD application with appropriate permissions:
  - `User.ReadWrite.All`
  - `Directory.ReadWrite.All`
- Azure AD Tenant ID, Client ID, and Client Secret

## Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd microsoft_graph_mcp_server
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your Azure credentials:

```env
AZURE_TENANT_ID=your-tenant-id-here
AZURE_CLIENT_ID=your-client-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
PORT=8000
```

### 3. Run Server

```bash
python server.py
```

The server will start on `http://localhost:8000` with SSE endpoint at `/sse`.

## Azure AD Setup

### Create App Registration

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Click "New registration"
3. Name: "MCP Graph Server"
4. Supported account types: "Single tenant"
5. Click "Register"

### Configure Permissions

1. Go to "API permissions"
2. Add permission → Microsoft Graph → Application permissions
3. Add:
   - `User.ReadWrite.All`
   - `Directory.ReadWrite.All`
4. Click "Grant admin consent"

### Create Client Secret

1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Add description and expiration
4. Copy the secret value immediately (you won't see it again)

### Get IDs

- **Tenant ID**: Overview → Directory (tenant) ID
- **Client ID**: Overview → Application (client) ID

## MCP Tools

### create_user

Create a new user in Azure AD.

```json
{
  "userPrincipalName": "john.doe@yourdomain.com",
  "displayName": "John Doe",
  "mailNickname": "john.doe",
  "password": "SecureP@ssw0rd!"
}
```

### read_user

Get user information.

```json
{
  "userId": "john.doe@yourdomain.com"
}
```

### update_user

Update user properties.

```json
{
  "userId": "john.doe@yourdomain.com",
  "displayName": "John M. Doe",
  "jobTitle": "Senior Engineer",
  "department": "Engineering"
}
```

### delete_user

Delete a user.

```json
{
  "userId": "john.doe@yourdomain.com"
}
```

## Using with Amazon Bedrock

This server implements the Remote MCP protocol and can be connected to Amazon Bedrock agents:

1. Deploy this server to a publicly accessible endpoint (AWS ECS, EC2, Lambda, etc.)
2. Configure your Bedrock agent with the server's SSE endpoint URL
3. The agent can now call the Microsoft Graph tools

## Architecture

- **MCP Server**: Official `mcp` Python SDK
- **Transport**: SSE (Server-Sent Events) for remote connections
- **Web Framework**: Starlette (lightweight ASGI)
- **Graph Client**: Official `msgraph-sdk`
- **Auth**: Azure Identity with client credentials flow

## Development

The server is built with minimal dependencies and clean async/await patterns for maximum performance and maintainability.

### Project Structure

```
microsoft_graph_mcp_server/
├── server.py           # Main MCP server implementation
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## Security Notes

- Never commit `.env` file
- Rotate client secrets regularly
- Use least-privilege permissions
- Enable Azure AD audit logging
- Consider using Managed Identity in production

## Troubleshooting

**Authentication fails**: Verify tenant ID, client ID, and secret are correct

**Permission denied**: Ensure admin consent granted for Graph API permissions

**Connection issues**: Check firewall rules and network connectivity

## License

MIT License - see LICENSE file for details
