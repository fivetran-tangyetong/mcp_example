## Key ideas

1. Data lives in `/data`
2. Read off by tools in `/tools`
  - Tools are recognized as such using `@mcp.tool()` identifier
  - Tools uses functions from `/utils`
3. Simply import in server file, no need to use anywhere
4. Add server to claude config
5. Now claude will have the tools inside developer mode

```json
{
  "mcpServers": {
    "mcp_example": {
      "command": "uv",
      "args": [
        "--directory",
        "...\\MCP_Example",
        "run",
        "main.py"
      ]
    }
  }
}
```

## Config

Located at ...\AppData\Roaming\Claude\claude_desktop_config.json
