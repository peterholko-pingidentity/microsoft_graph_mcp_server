#!/usr/bin/env python3
"""Remote MCP Server for Microsoft Graph API with Amazon Bedrock support."""

import os
import json
import logging
import asyncio
from typing import Any
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.middleware.cors import CORSMiddleware
from msgraph import GraphServiceClient
from azure.identity import ClientSecretCredential

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        Tool(
          name="list_users",
          description="List users in the Azure AD tenant",
          inputSchema={
            "type": "object",
            "properties": {
                "top": {"type": "integer", "description": "Number of users to return (default 10, max 999)", "default": 10},
            },
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
        
        elif name == "list_users":
            # Get the 'top' parameter, default to 10 if not provided
            top_count = arguments.get("top", 10)
    
            # 1. Define a local function to handle the configuration
            def configure_query(config):
                config.query_parameters.top = top_count
    
            # 2. Pass that function to the request
            users_page = await graph_client.users.get(
                request_configuration=configure_query
            )
    
            user_list = []
            if users_page and users_page.value:
                for user in users_page.value:
                    user_list.append({
                        "id": user.id,
                        "userPrincipalName": user.user_principal_name,
                        "displayName": user.display_name,
                        "mail": user.mail
                    })

            return [TextContent(
                type="text", 
                text=json.dumps({"users": user_list, "count": len(user_list)}, indent=2)
            )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        # Parse Microsoft Graph API errors for better messages
        error_msg = str(e)
        if "Request_ResourceNotFound" in error_msg:
            return [TextContent(type="text", text=f"Error: User '{arguments.get('userId', 'unknown')}' not found in Azure AD. Please verify the user ID or userPrincipalName.")]
        elif "Request_BadRequest" in error_msg:
            return [TextContent(type="text", text=f"Error: Invalid request. Please check the parameters: {error_msg}")]
        elif "Authorization_RequestDenied" in error_msg or "Forbidden" in error_msg:
            return [TextContent(type="text", text=f"Error: Permission denied. Ensure the app has the required Graph API permissions (User.ReadWrite.All).")]
        else:
            return [TextContent(type="text", text=f"Error: {error_msg}")]


# Don't use SseServerTransport - it has complex session management
# Instead, implement simple HTTP streaming directly
logger.info("Creating MCP server handler")

async def mcp_asgi_app(scope, receive, send):
    """Raw ASGI application for handling MCP connections."""
    logger.info("="*80)
    logger.info(f"========== NEW REQUEST ==========")
    logger.info("="*80)
    logger.info(f"Request type: {scope.get('type')}")
    logger.info(f"Request method: {scope.get('method')}")
    logger.info(f"Request path: {scope.get('path')}")
    logger.info(f"Query string: {scope.get('query_string', b'').decode()}")
    logger.info(f"Client: {scope.get('client')}")
    logger.info(f"Scheme: {scope.get('scheme')}")
    logger.info(f"Server: {scope.get('server')}")

    # Parse and log headers nicely
    headers_dict = {}
    for key, value in scope.get('headers', []):
        headers_dict[key.decode()] = value.decode()
    logger.info("Headers:")
    for k, v in headers_dict.items():
        logger.info(f"  {k}: {v}")

    logger.info("="*80)

    if scope["type"] != "http":
        logger.warning(f"Non-HTTP request type: {scope['type']}")
        return

    # Only handle /mcp path
    if scope["path"] != "/mcp":
        logger.warning(f"Path mismatch: {scope['path']} != /mcp")
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Not Found",
        })
        return

    if scope["method"] == "GET":
        logger.info(">>> Handling GET request - establishing SSE connection")
        # For SSE clients, establish a server-sent events stream
        import uuid
        session_id = str(uuid.uuid4())
        logger.info(f">>> Created session: {session_id}")

        # Send SSE headers
        logger.info(">>> Sending SSE response headers")
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/event-stream"],
                [b"cache-control", b"no-cache"],
                [b"connection", b"keep-alive"],
            ],
        })
        logger.info(">>> SSE headers sent successfully")

        # Send the endpoint event with session_id
        endpoint_event = f"event: endpoint\ndata: /mcp?session_id={session_id}\n\n"
        logger.info(f">>> Sending endpoint event: {endpoint_event.strip()}")
        await send({
            "type": "http.response.body",
            "body": endpoint_event.encode(),
            "more_body": True,
        })
        logger.info(">>> Endpoint event sent successfully")

        logger.info(f">>> SSE connection fully established with session {session_id}")
        logger.info(f">>> Client should now POST to: /mcp?session_id={session_id}")

        # Keep connection alive - wait for disconnect
        try:
            message_count = 0
            while True:
                message = await receive()
                message_count += 1
                logger.debug(f">>> SSE session {session_id}: received message #{message_count}: {message}")

                if message["type"] == "http.disconnect":
                    logger.info(f">>> Session {session_id} DISCONNECTED after {message_count} messages")
                    break
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f">>> SSE connection error for session {session_id}: {e}", exc_info=True)

    elif scope["method"] == "POST":
        logger.info("<<< Handling POST request - direct message handling")

        # Check for session_id in query string (for SSE clients)
        query_string = scope.get("query_string", b"").decode()
        session_id = None
        if query_string:
            from urllib.parse import parse_qs
            params = parse_qs(query_string)
            session_id = params.get("session_id", [None])[0]
            logger.info(f"<<< POST with session_id: {session_id}")
        else:
            logger.info("<<< POST without session_id (direct client)")

        try:
            # Read the POST body
            logger.info("<<< Reading POST body...")
            body_parts = []
            chunk_count = 0
            while True:
                message = await receive()
                chunk_count += 1
                logger.debug(f"<<< Received chunk #{chunk_count}: {message}")

                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        logger.info(f"<<< Body complete after {chunk_count} chunks")
                        break

            full_body = b"".join(body_parts)
            logger.info(f"<<< Total body size: {len(full_body)} bytes")
            logger.info(f"<<< Body preview: {full_body[:200]}")

            request_data = json.loads(full_body)
            logger.info(f"<<< Parsed JSON-RPC request:")
            logger.info(f"<<<   Method: {request_data.get('method')}")
            logger.info(f"<<<   ID: {request_data.get('id')}")
            logger.info(f"<<<   Params: {request_data.get('params', {})}")

            # Import needed for JSON-RPC handling
            from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError

            # Handle the JSON-RPC request
            logger.info(f"<<< Processing method: {request_data.get('method')}")

            if request_data.get("method") == "initialize":
                logger.info("<<< Handling 'initialize' request")
                response = {
                    "jsonrpc": "2.0",
                    "id": request_data["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "microsoft-graph-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
                logger.info("<<< Initialize response prepared")

            elif request_data.get("method") == "tools/list":
                logger.info("<<< Handling 'tools/list' request")
                tools = await list_tools()
                logger.info(f"<<< Found {len(tools)} tools")
                response = {
                    "jsonrpc": "2.0",
                    "id": request_data["id"],
                    "result": {
                        "tools": [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema
                            }
                            for tool in tools
                        ]
                    }
                }
                logger.info(f"<<< Tools list response prepared with tools: {[t.name for t in tools]}")

            elif request_data.get("method") == "tools/call":
                tool_name = request_data["params"]["name"]
                arguments = request_data["params"].get("arguments", {})
                logger.info(f"<<< Handling 'tools/call' request for tool: {tool_name}")
                logger.info(f"<<< Tool arguments: {arguments}")

                result = await call_tool(tool_name, arguments)
                logger.info(f"<<< Tool execution completed, result: {result}")

                response = {
                    "jsonrpc": "2.0",
                    "id": request_data["id"],
                    "result": {
                        "content": [{"type": r.type, "text": r.text} for r in result]
                    }
                }
                logger.info("<<< Tool call response prepared")

            else:
                logger.warning(f"<<< Unknown method: {request_data.get('method')}")
                response = {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {request_data.get('method')}"
                    }
                }

            response_body = json.dumps(response).encode()
            logger.info(f"<<< Response body size: {len(response_body)} bytes")
            logger.info(f"<<< Response preview: {response_body[:300]}")

            logger.info("<<< Sending HTTP 200 response...")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(response_body)).encode()],
                ],
            })
            logger.info("<<< Response headers sent")

            await send({
                "type": "http.response.body",
                "body": response_body,
            })
            logger.info("<<< Response body sent - REQUEST COMPLETE")
            logger.info("="*80)

        except Exception as e:
            logger.error("="*80)
            logger.error(f"<<< ERROR in POST handler: {e}", exc_info=True)
            logger.error("="*80)

            error_response = {
                "jsonrpc": "2.0",
                "id": request_data.get("id") if 'request_data' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            error_body = json.dumps(error_response).encode()
            logger.error(f"<<< Sending error response: {error_body[:200]}")

            try:
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": error_body,
                })
                logger.error("<<< Error response sent")
            except Exception as send_error:
                logger.error(f"<<< Failed to send error response: {send_error}", exc_info=True)
    else:
        logger.warning(f"Unsupported method: {scope['method']}")
        await send({
            "type": "http.response.start",
            "status": 405,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Method Not Allowed",
        })

# Wrap with CORS middleware
app = CORSMiddleware(
    mcp_asgi_app,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
