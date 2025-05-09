import os
import json
import time
import requests
import dotenv
from sseclient import SSEClient
from google.cloud import aiplatform
from google.ai.generative.language import ChatModel

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

# 1) Apify & GitHub credentials
APIFY_TOKEN   = os.getenv("APIFY_TOKEN", "<YOUR_APIFY_API_TOKEN>")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "<YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>")
GITHUB_OWNER  = "fivetran-tangyetong"
GITHUB_REPO   = "NerveAnatomy"
REPO_URL      = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

# 2) Google Cloud / Vertex AI (Gemini chat)
GCP_PROJECT   = "your-gcp-project-id"
GCP_LOCATION  = "us-central1"  # adjust as needed

# 3) Apify MCP endpoints & actor IDs
MCP_BASE      = "https://actors-mcp-server.apify.actor"
ACTOR_CODE    = "apify/github-scraper"
ACTOR_ISSUES  = "apify/github-issues-scraper"


# ─── Helpers: MCP Session + RPC Calls ──────────────────────────────────────────

def start_mcp_session(actors):
    """
    Open an SSE session to the Apify MCP server and return the sessionId.
    """
    url = (
        f"{MCP_BASE}/sse?"
        f"token={APIFY_TOKEN}&actors={','.join(actors)}"
    )
    for event in SSEClient(url):
        data = json.loads(event.data)
        if "sessionId" in data:
            return data["sessionId"]
    raise RuntimeError("Failed to obtain sessionId from MCP SSE")


def mcp_call(session_id, actor_name, run_input):
    """
    Send a JSON-RPC tools/call to invoke the given actor with run_input.
    """
    url = f"{MCP_BASE}/message?token={APIFY_TOKEN}&session_id={session_id}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": actor_name,
            "arguments": run_input,
        },
    }
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


def collect_dataset_items(dataset_id):
    """
    Helper to page through Apify dataset items via the HTTP API.
    """
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true&format=json&limit=1000"
    resp = requests.get(url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
    resp.raise_for_status()
    return resp.json()


# ─── 1) Kick off both actors via MCP ────────────────────────────────────────────

session = start_mcp_session([ACTOR_CODE, ACTOR_ISSUES])

# 1a) Scrape code files
code_run = mcp_call(session, ACTOR_CODE, {
    "token":       GITHUB_TOKEN,
    "repoUrl":     REPO_URL,
    "mode":        "repo",
    "includePaths":["**/*.py","**/*.js","**/*.md"],
})
code_dataset = code_run["result"]["defaultDatasetId"]

# 1b) Scrape issues
issues_run = mcp_call(session, ACTOR_ISSUES, {
    "token": GITHUB_TOKEN,
    "owner": GITHUB_OWNER,
    "repo":  GITHUB_REPO,
    "state": "open"
})
issues_dataset = issues_run["result"]["defaultDatasetId"]


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


# ─── 3) Initialize Vertex AI & Gemini chat model ──────────────────────────────

aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
chat_model = ChatModel.from_pretrained("chat-bison-001")


# ─── 4) Build and send the chat prompt ──────────────────────────────────────────

system_prompt = (
    "You are a senior software engineer. "
    "The user will provide GitHub code and open issues. "
    "Help them understand the repo’s purpose, main modules, "
    "and summarize the top pain points from the issues."
)

user_prompt = (
    f"Here is the repository code for {GITHUB_OWNER}/{GITHUB_REPO}:\n\n"
    f"{code_text}\n\n"
    "And here are the open issues:\n\n"
    f"{issues_text}\n\n"
    "Please provide a clear, concise chat-style summary."
)

response = chat_model.chat(
    context=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ],
    temperature=0.1,
    max_output_tokens=1024,
)

print("\n===== Chat Summary =====\n")
print(response.choices[0].message.content)
