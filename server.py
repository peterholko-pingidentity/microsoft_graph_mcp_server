#!/usr/bin/env python3
"""Remote MCP Server for Microsoft Graph API with Amazon Bedrock support."""

import os
import json
from typing import Any
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
from msgraph import GraphServiceClient
from azure.identity import ClientSecretCredential

load_dotenv()

# Microsoft Graph API credentials
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

# Initialize Graph client
credential = ClientSecretCredential(TENANT_ID, CLIENT_ID, CLIENT_SECRET)
graph_client = GraphServiceClient(credential)

# Create MCP server
mcp_server = Server("microsoft-graph-mcp")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Microsoft Graph user management tools."""
    return [
        Tool(
            name="create_user",
            description="Create a new user in Azure AD",
            inputSchema={
                "type": "object",
                "properties": {
                    "userPrincipalName": {"type": "string", "description": "User's email address"},
                    "displayName": {"type": "string", "description": "User's display name"},
                    "mailNickname": {"type": "string", "description": "Mail alias"},
                    "password": {"type": "string", "description": "Initial password"},
                },
                "required": ["userPrincipalName", "displayName", "mailNickname", "password"],
            },
        ),
        Tool(
            name="read_user",
            description="Get user information from Azure AD",
            inputSchema={
                "type": "object",
                "properties": {
                    "userId": {"type": "string", "description": "User ID or userPrincipalName"},
                },
                "required": ["userId"],
            },
        ),
        Tool(
            name="update_user",
            description="Update an existing user in Azure AD",
            inputSchema={
                "type": "object",
                "properties": {
                    "userId": {"type": "string", "description": "User ID or userPrincipalName"},
                    "displayName": {"type": "string", "description": "New display name"},
                    "jobTitle": {"type": "string", "description": "Job title"},
                    "department": {"type": "string", "description": "Department"},
                },
                "required": ["userId"],
            },
        ),
        Tool(
            name="delete_user",
            description="Delete a user from Azure AD",
            inputSchema={
                "type": "object",
                "properties": {
                    "userId": {"type": "string", "description": "User ID or userPrincipalName"},
                },
                "required": ["userId"],
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution for Microsoft Graph operations."""
    try:
        if name == "create_user":
            from msgraph.generated.models.user import User
            from msgraph.generated.models.password_profile import PasswordProfile

            user = User()
            user.user_principal_name = arguments["userPrincipalName"]
            user.display_name = arguments["displayName"]
            user.mail_nickname = arguments["mailNickname"]
            user.account_enabled = True

            password_profile = PasswordProfile()
            password_profile.password = arguments["password"]
            password_profile.force_change_password_next_sign_in = True
            user.password_profile = password_profile

            result = await graph_client.users.post(user)
            return [TextContent(
                type="text",
                text=f"User created successfully: {result.id}\n{json.dumps({'id': result.id, 'userPrincipalName': result.user_principal_name, 'displayName': result.display_name}, indent=2)}"
            )]

        elif name == "read_user":
            user = await graph_client.users.by_user_id(arguments["userId"]).get()
            user_data = {
                "id": user.id,
                "userPrincipalName": user.user_principal_name,
                "displayName": user.display_name,
                "mail": user.mail,
                "jobTitle": user.job_title,
                "department": user.department,
                "accountEnabled": user.account_enabled,
            }
            return [TextContent(type="text", text=json.dumps(user_data, indent=2))]

        elif name == "update_user":
            from msgraph.generated.models.user import User

            user = User()
            if "displayName" in arguments:
                user.display_name = arguments["displayName"]
            if "jobTitle" in arguments:
                user.job_title = arguments["jobTitle"]
            if "department" in arguments:
                user.department = arguments["department"]

            await graph_client.users.by_user_id(arguments["userId"]).patch(user)
            return [TextContent(type="text", text=f"User {arguments['userId']} updated successfully")]

        elif name == "delete_user":
            await graph_client.users.by_user_id(arguments["userId"]).delete()
            return [TextContent(type="text", text=f"User {arguments['userId']} deleted successfully")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# Starlette app for SSE transport
async def handle_sse(request):
    """Handle SSE connections for remote MCP protocol."""
    async with SseServerTransport("/messages") as transport:
        await mcp_server.run(
            transport.read_stream,
            transport.write_stream,
            mcp_server.create_initialization_options(),
        )


async def handle_messages(request):
    """Handle message POST requests."""
    async with SseServerTransport("/messages") as transport:
        await transport.handle_post_message(request)


app = Starlette(
    debug=True,
    routes=[
        Route("/mcp", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
