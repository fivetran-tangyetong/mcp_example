import os
import json
import requests
from dotenv import load_dotenv
from sseclient import SSEClient

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "<YOUR_APIFY_API_TOKEN>")
# The MCP server endpoint
MCP_BASE    = "https://actors-mcp-server.apify.actor"
# The Actor ID for your X/Twitter scraper in Apify Store
ACTOR_X     = "apidojo/twitter-scraper-lite"

# ─── Helpers: MCP Session + RPC Calls ──────────────────────────────────────────

def start_mcp_session():
    """
    Open the SSE stream and include ACTOR_X so that this Actor
    is available as a tool alongside the built-in helpers.
    """
    sse_url = f"{MCP_BASE}/sse?token={APIFY_TOKEN}&actors={ACTOR_X}"
    client = SSEClient(sse_url)
    for event in client:
        if event.data and "sessionId=" in event.data:
            # sessionId comes in the 'endpoint' event
            return client, event.data.split("sessionId=")[1]
    raise RuntimeError("Failed to obtain sessionId from MCP SSE")

def mcp_call(client, session_id, tool_name, args, call_id):
    """
    Send a JSON-RPC call to the MCP server and wait for the matching SSE reply.
    """
    post_url = f"{MCP_BASE}/message?token={APIFY_TOKEN}&session_id={session_id}"
    payload = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        }
    }
    resp = requests.post(post_url, json=payload, headers={"Content-Type": "application/json"})
    resp.raise_for_status()

    for event in client:
        if event.event == "message" and event.data:
            data = json.loads(event.data)
            if data.get("id") == call_id:
                if "error" in data:
                    raise RuntimeError(f"Actor error: {data['error']}")
                return data["result"]
    raise RuntimeError(f"No response received for call id={call_id}")

def collect_dataset_items(dataset_id):
    """
    Page through an Apify dataset via the HTTP API.
    """
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true&format=json&limit=1000"
    resp = requests.get(url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
    resp.raise_for_status()
    return resp.json()

# ─── Main Flow ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1) Start MCP session (loads ACTOR_X as a tool)
    client, session = start_mcp_session()

    # 2) Run the X scraper Actor to get Trump’s latest 100 posts
    run_res = mcp_call(
        client, session,
        ACTOR_X,
        {
            "searchQueries": ["from:realDonaldTrump"],
            "tweetsDesired": 100,
            "dev_dataset_clear": True
        },
        call_id=1
    )
    print(f"✨ Scraping started, run_res: {run_res}")

    dataset_id = run_res["defaultDatasetId"]
    print(f"✨ Scraping started, dataset ID: {dataset_id}")

    # 3) Fetch the tweets from the dataset and print them
    tweets = collect_dataset_items(dataset_id)
    for t in tweets:
        timestamp = t.get("createdAt") or t.get("date") or "[no timestamp]"
        text      = t.get("text")      or t.get("content")  or "[no text field]"
        print(f"{timestamp}  ·  {text}")
