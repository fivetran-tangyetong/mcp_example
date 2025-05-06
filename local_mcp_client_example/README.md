## Some Takeaways

### Connect to the MCP Server
We can use boilerplate code to set up the connection to the MCP server (our weather API MCP server)

```python
server_params = StdioServerParameters(command=command, args=[server_script_path], env=None)

stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
self.stdio, self.write = stdio_transport
self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
```

Since we are calling the MCP server that is local, we can use `stdio`. 
> The stdio transport enables communication through standard input and output streams. This is particularly useful for local integrations and command-line tools.

As per the docs, use `stdio` when:
- Building command-line tools
- Implementing local integrations
- Needing simple process communication
- Working with shell scripts

For remote servers, use `sse` (Server-Sent Events). 
> SSE transport enables server-to-client streaming with HTTP POST requests for client-to-server communication.

Use `sse` when:
- Only server-to-client streaming is needed
- Working with restricted networks
- Implementing simple updates

### Get MCP Server tools

We then expose the tools from the MCP Server using:
```python
response = await self.session.list_tools()
self.converted_tools = [convert_tool_format(t) for t in response.tools]
```

This gets the tools available, and converts it into JSON for input later.

### Query

The query bit is pretty simple, there are 2 scenarios here:

#### Scenario 1: General LLM output
1. User inputs a generic LLM input that does not use a tool, i.e. "How are you doing"
2. LLM decides that it does not need a tool
3. LLM generates a response
4. We output the text

#### Scenario 2: LLM output that requires tool usage
1. User inputs a LLM input that uses a tool, i.e. "What is the weather forecast of Oakland, CA?"
2. LLM decides that it needs a tool, i.e. `get_forecast`
3. It returns a response JSON that has a `tool_calls` field
4. We see that, and parse the field for the tool name and arguments
5. We call the tool using `self.session.call_tool(name, args)`
6. We get a response from the tool
7. We tell the LLM the response
8. LLM generates a natural language response using the results
9. We output that response

## Key Takeaways
The most important point here is that the **LLM is not connected the the server**.

The LLM decides that what tool usage is necessary, and tell the client it is necessary, with the tool name and args as well.
It is up to the **client**, to call the tool, then pass the results back into the LLM for natural language encoding of the results.

For local MCP servers, when we edit the claude for desktop config JSON, we are telling it to run `uv run //[YOUR_DIRECTORU//[SERVER_FILE].py` for example.
Claude for Desktop (the LLM), then sets up a client that connects to the MCP server (locally).

The LLM here can have multiple clients having 1:1 connections with multiple MCP servers, and handles the tool calling under the hood for you, but at the end of the day,
the LLM itself is not firing off the MCP tools by itself.

<img width="687" alt="Screenshot 2025-05-06 at 4 40 50 PM" src="https://github.com/user-attachments/assets/48f92b44-3ed2-4dda-a1d3-0461571620a7" />

