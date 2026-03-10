# Slack Private Data Exporter

Export your **DMs, Group DMs, and Private Channels** from Slack — the data that Slack's admin export **does not** include.

## Quick Start

```bash
git clone <this-repo-url>
cd slack-scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env → paste your token and cookie (see "Get your Slack credentials" below)
python slack_export.py --oldest 2025-01-01 --zip slack_private_export
```

That's it. You'll get a `slack_private_export.zip` with all your DMs, Group DMs, and Private Channels from Jan 2025 onwards.

---

## Why?

Slack's built-in admin export only gives you **public channels**. If you want your DMs and private conversations, you're out of luck — unless you use this tool.

## What you get

```
slack_export/
├── users.json                          # all workspace users
├── dms.json                            # DM metadata
├── mpims.json                          # Group DM metadata
├── groups.json                         # Private channel metadata
├── channels.json                       # empty (use admin export for public channels)
├── dm--username/                       # 1:1 DM messages
│   ├── 2025-01-15.json
│   └── 2025-02-20.json
├── mpdm-user1--user2--user3-1/         # Group DM messages
│   └── 2025-03-01.json
└── private-channel-name/               # Private channel messages
    └── 2025-04-10.json
```

## Setup

### 1. Clone this repo

```bash
git clone <this-repo-url>
cd slack-scraper
pip install -r requirements.txt
```

### 2. Get your Slack credentials

You need **two things** from your browser — a **token** and a **cookie**. Both are grabbed from the same place.

> Make sure you're logged into your Slack workspace in the browser (e.g. `yourworkspace.slack.com`), NOT the desktop app.

#### Token (`xoxc-...`)

1. Open your Slack workspace in **Chrome/Edge/Firefox**
2. Press **F12** to open Developer Tools
3. Go to the **Network** tab
4. In the filter bar at the top, type `api` to filter requests
5. Now click around in Slack — open any channel, send a message, do anything
6. You'll see API requests appear (like `conversations.history`, `chat.postMessage`, etc.)
7. Click on any one of those requests
8. Go to the **Payload** tab (Chrome) or **Request** tab (Firefox)
9. Look for `token` in the form data — it looks like:
   ```
   token: xoxc-754203323143-8551802506338-...
   ```
10. Copy the **entire token value** starting with `xoxc-`

#### Cookie (`xoxd-...`)

1. Still in Developer Tools (F12), go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
2. In the left sidebar, expand **Cookies**
3. Click on `https://app.slack.com`
4. In the cookie list, find the one named **`d`**
5. Double-click the **Value** column to select it — it looks like:
   ```
   xoxd-0kl8TF2FPLxBasHSEregYKqd...
   ```
6. Copy the **entire value** starting with `xoxd-`

> **Can't find it?** The `d` cookie might be URL-encoded (contains `%2F`, `%2B`, etc.) — that's fine, copy it as-is.

### 3. Create `.env` file

```bash
cp .env.example .env
```

Edit `.env` and paste your token and cookie:

```
SLACK_TOKEN=xoxc-your-token-here
SLACK_COOKIE=xoxd-your-cookie-here
```

## Usage

### Export everything (DMs + Group DMs + Private Channels)

```bash
python slack_export.py
```

### Export with date range

```bash
# Only messages from 2025 onwards
python slack_export.py --oldest 2025-01-01

# Messages between specific dates
python slack_export.py --oldest 2025-01-01 --latest 2026-01-01
```

### Export as ZIP

```bash
python slack_export.py --oldest 2025-01-01 --zip my_slack_export
```

### Dry run (see what would be exported)

```bash
python slack_export.py --dry-run
```

### Export only specific types

```bash
# Only 1:1 DMs
python slack_export.py --types im

# Only private channels
python slack_export.py --types private_channel

# Only group DMs
python slack_export.py --types mpim

# Combine types
python slack_export.py --types im,mpim
```

### Pass credentials directly (instead of .env)

```bash
python slack_export.py --token "xoxc-..." --cookie "xoxd-..."
```

## View the export

```bash
pip install slack-export-viewer
slack-export-viewer -z my_slack_export.zip
```

This opens a local web UI that looks like Slack.

## Rate Limits

Slack allows ~50 API calls per minute. The tool handles rate limiting automatically — it pauses and retries when throttled. Expect:

| Data size | Estimated time |
|-----------|---------------|
| 50 conversations, ~500 msgs each | ~5 minutes |
| 100 conversations, ~2000 msgs each | ~20 minutes |
| 500+ conversations | 1-2 hours |

## Notes

- Your token and cookie are **sensitive** — they give full access to your Slack account. Never commit the `.env` file.
- Tokens expire after a few days. If you get auth errors, grab fresh ones from the browser.
- This tool only exports data **you have access to** — it can't see other people's DMs or channels you're not in.
- For **public channels**, use Slack's built-in admin export (Workspace Settings → Import/Export Data).

## License

MIT
