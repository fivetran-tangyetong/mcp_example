import os
import json
import requests
from dotenv import load_dotenv
from sseclient import SSEClient
from google import genai
from google.genai import types
from urllib.parse import quote_plus

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

# 1) Apify & GitHub credentials
APIFY_TOKEN   = os.getenv("APIFY_TOKEN", "<YOUR_APIFY_API_TOKEN>")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "<YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>")
GITHUB_OWNER  = "fivetran-tangyetong"
GITHUB_REPO   = "NerveAnatomy"
REPO_URL      = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

# 2) Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "<DEFAULT_GOOGLE_API_KEY>")
GEMINI_MODEL  = "gemini-2.5-pro-exp-03-25"

# 3) Apify MCP endpoints & actor IDs
MCP_BASE      = "https://actors-mcp-server.apify.actor"
ACTOR_CODE    = "apify/github-scraper"
ACTOR_ISSUES  = "apify/github-issues-scraper"


# ─── Helpers: MCP Session + RPC Calls ──────────────────────────────────────────

def start_mcp_session():
    """Open the SSE stream and extract the session_id."""
    sse_url = f"{MCP_BASE}/sse?token={APIFY_TOKEN}"
    client = SSEClient(sse_url)
    for event in client:
        if not event.data or not event.data.strip():
            continue
        # look for the sessionId in the initial 'endpoint' event
        if "sessionId=" in event.data:
            session_id = event.data.split("sessionId=")[1]
            return client, session_id
    raise RuntimeError("Failed to obtain sessionId from MCP SSE")


def mcp_call(client, session_id, actor_name, run_input, call_id):
    """
    Send a JSON-RPC call, then block until we see a matching SSE 'message' with id==call_id.
    Returns the 'result' dict from that JSON-RPC response.
    """
    post_url = f"{MCP_BASE}/message?token={APIFY_TOKEN}&session_id={session_id}"
    payload = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": actor_name,
            "arguments": run_input,
        },
    }
    resp = requests.post(post_url, json=payload, headers={"Content-Type": "application/json"})
    resp.raise_for_status()
    print(f">>> Called {actor_name} (id={call_id}) → {resp.text.strip()}")

    # now wait for the matching JSON-RPC reply over SSE
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
    Helper to page through Apify dataset items via the HTTP API.
    """
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true&format=json&limit=1000"
    resp = requests.get(url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
    resp.raise_for_status()
    return resp.json()


# ─── 1) Kick off both actors via MCP ────────────────────────────────────────────

client, session = start_mcp_session()

# 1a) Scrape code files
code_run = mcp_call(
    client,
    session,
    ACTOR_CODE,
    {
        "token":       GITHUB_TOKEN,
        "repoUrl":     f"https://github.com/fivetran-tangyetong/NerveAnatomy",
        "mode":        "repo",
        "includePaths":["**/*.py","**/*.js","**/*.md","**/*.tsx","**/*.ts"],
    },
    call_id=1,
)
code_dataset = code_run["defaultDatasetId"]

# 1b) Scrape issues
issues_run = mcp_call(
    client,
    session,
    ACTOR_ISSUES,
    {
        "token": GITHUB_TOKEN,
        "owner": "fivetran-tangyetong",
        "repo":  "NerveAnatomy",
        "state": "open",
    },
    call_id=2,
)
issues_dataset = issues_run["defaultDatasetId"]


# ─── 2) Pull down the results via the Apify HTTP API ────────────────────────────

code_items   = collect_dataset_items(code_dataset)
issues_items = collect_dataset_items(issues_dataset)

code_text   = "\n\n".join(
    f"### {item['path']}\n```{item.get('content','')}```"
    for item in code_items
)

issues_text = "\n\n".join(
    f"#### #{i['number']} {i['title']}\n{i.get('body','')}"
    for i in issues_items
)


# ─── 3) Initialize Gemini chat model ──────────────────────────────

client = genai.Client(api_key=GOOGLE_API_KEY)

# ─── 4) Build and send the chat prompt ──────────────────────────────────────────

system_prompt = (
    "You are a senior software engineer. "
    "The user will provide GitHub code and open issues. "
    "Help them understand the repo's purpose, main modules, "
    "and summarize the top pain points from the issues."
)

user_prompt = (
    f"Here is the repository code for {GITHUB_OWNER}/{GITHUB_REPO}:\n\n"
    f"{code_text}\n\n"
    "And here are the open issues:\n\n"
    f"{issues_text}\n\n"
    "Please provide a clear, concise chat-style summary."
)

chat = client.chats.create(
    model=GEMINI_MODEL,
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
        max_output_tokens=1024,
    ),
)

response = chat.send_message(user_prompt)
print("\n===== Chat Summary =====\n")
print(response.text)
