## Goal

Rough examples on how to run specific MCP server / clients:

## `local_mcp_client_example`

```bash
uv run client.py ../local_mcp_remote_resources_example/main.py
```

This runs an example CLI MCP client instance that uses any LLM model that has tool integration:
- Claude
- Gemini
- Mistal
- ...

It uses tools from other MCP servers, specifically the local MCP server in the same repository that calls the weather API

## `local_mcp_local_resources_example`

```bash
uv run main.py
```

This MCP server instance simply calls tools that access local resources, in this case, csvs and parquet files.

The MCP server can then be exposed through Claude for Desktop

## `local_mcp_remote_resources_example`
```bash
uv run main.py
```

This MCP server instance simply calls tools that access remote resources, in this case, calling the weather AI.

The MCP server can then be exposed through Claude for Desktop
