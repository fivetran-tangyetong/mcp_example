import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
import re

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1"
if not OPENROUTER_API_KEY:
  raise RuntimeError("Missing OPENROUTER_API_KEY in environment")

EXTRA_BODY_SAFETY = {
  # "safetySettings": [
  #   {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
  #   {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
  #   {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_NONE"},
  #   {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE"},
  # ]
}

DEEPSEEK_MODEL = 'deepseek/deepseek-chat:free'
GEMINI_MODEL_PRO_EXP = 'google/gemini-2.5-pro-exp-03-25'
GEMINI_MODEL_FLASH_EXP = 'google/gemini-flash-1.5-8b-exp'
MISTRAL_SMALL = 'mistralai/mistral-small-3.1-24b-instruct:free'
MISTAL_7B_FREE = 'mistralai/mistral-7b-instruct:free'

MODEL = MISTAL_7B_FREE

MAX_TOKENS = 1000

def convert_tool_format(tool):
  props    = tool.inputSchema["properties"] if tool.inputSchema else {}
  required = tool.inputSchema["required"]   if tool.inputSchema else []
  
  converted_tool = {
    "type": "function",
    "function": {
      "name": tool.name,
      "description": tool.description,
      "parameters": {
        "type": "object",
        "properties": props,
        "required":   required
      }
    }
  }
  return converted_tool

class MCPClient:
  def __init__(self):
    # Initialize session and client objects
    self.session: Optional[ClientSession] = None
    self.exit_stack = AsyncExitStack()
    self.openai = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_API_URL)
    self.messages = []

  async def connect_to_server(self, server_script_path: str):
    """Connect to an MCP server

    Args:
        server_script_path: Path to the server script (.py or .js)
    """
    is_python = server_script_path.endswith(".py")
    is_js = server_script_path.endswith(".js")
    if not (is_python or is_js):
      raise ValueError("Server script must be a .py or .js file")

    command = "python" if is_python else "node"
    server_params = StdioServerParameters(command=command, args=[server_script_path], env=None)

    stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
    self.stdio, self.write = stdio_transport
    self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

    await self.session.initialize()

    # List available tools
    response = await self.session.list_tools()
    self.converted_tools = [convert_tool_format(t) for t in response.tools]

    print("Connected with tools:", [t["function"]["name"] for t in self.converted_tools])

  async def process_query(self, query: str) -> str:
    # 1) Add the user prompt
    self.messages.append({"role": "user", "content": query})

    # 2) Retrieve tools and ask the LLM
    tools = [t for t in self.converted_tools if t is not None]

    response = self.openai.chat.completions.create(
      model=MODEL, tools=tools, messages=self.messages
    )

    print(response)
    
    self.messages.append(response.choices[0].message.model_dump())

    final_text = []
    content = response.choices[0].message

    # 3) If the LLM wants to call a tool, do it and return its output
    if content.tool_calls is not None:
      call = content.tool_calls[0]
      name = call.function.name
      raw = call.function.arguments

      # parse JSON (with fallback)
      try:
          args = json.loads(raw)
      except json.JSONDecodeError:
        matches = re.findall(r'\{[^{}]*\}', raw)
        if not matches:
            raise
        args = json.loads(matches[-1])

      tool_result = await self.session.call_tool(name, args)

      print(f"\nTool result: {tool_result})")

      # record tool output in history
      self.messages.append({
        "role": "tool",
        "name": name,
        "tool_call_id": call.id,
        "content": tool_result.content
      })

      print(f"\n Self Message: {self.messages})")

      response = self.openai.chat.completions.create(
        model=MODEL,
        tools=tools,
        max_tokens=MAX_TOKENS,
        messages=self.messages,
      )

      print(f"\n Self Message: {self.messages})")
      print(f"\n Response: {response})")

      final_text.append(response.choices[0].message.content)
    else:
      final_text.append(content.content)

    return "\n".join(final_text)
  
  async def chat_loop(self):
    """Run an interactive chat loop"""
    print("\nMCP Client Started!")
    print("Type your queries or 'quit' to exit.")

    while True:
      try:
        query = input("\nQuery: ").strip()

        if query.lower() == "quit":
          break

        response = await self.process_query(query)
        print("\n" + response)

      except Exception as e:
        print(f"\nError: {str(e)}")

  async def cleanup(self):
    """Clean up resources"""
    await self.exit_stack.aclose()


async def main():
  if len(sys.argv) < 2:
    print("Usage: python client.py <path_to_server_script>")
    sys.exit(1)

  client = MCPClient()
  try:
    await client.connect_to_server(sys.argv[1])
    await client.chat_loop()
  finally:
      await client.cleanup()


if __name__ == "__main__":
  import sys

  asyncio.run(main())
