"""Phân hệ kết nối AI Chatbot & Agent (MCP JSON-RPC 2.0 + Multi-Provider LLM Tool Calling) cho Karius Academic System (KAS)."""

from karius_academic_system.ai.bridge import (
    AI_PROVIDERS,
    AIConfig,
    ai_config_path,
    chat_with_agent,
    load_ai_config,
    save_ai_config,
)
from karius_academic_system.ai.mcp_server import (
    generate_mcp_client_config,
    handle_mcp_jsonrpc,
    serve_mcp_stdio,
)
from karius_academic_system.ai.tools import (
    execute_agent_tool,
    get_agent_tool_schemas,
    get_openai_tools_spec,
)

__all__ = [
    "AIConfig",
    "AI_PROVIDERS",
    "ai_config_path",
    "load_ai_config",
    "save_ai_config",
    "chat_with_agent",
    "generate_mcp_client_config",
    "handle_mcp_jsonrpc",
    "serve_mcp_stdio",
    "execute_agent_tool",
    "get_agent_tool_schemas",
    "get_openai_tools_spec",
]
