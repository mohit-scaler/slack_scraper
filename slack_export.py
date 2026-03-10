"""
Slack Private Data Exporter

Exports DMs, Group DMs, and Private Channels from Slack using xoxc- token + cookie.
This data is NOT available via Slack's admin export (which only covers public channels).

Based on zach-snell/slack-export, rewritten to support xoxc- token auth and date filtering.
"""

import json
import argparse
import os
import shutil
from datetime import datetime
from time import sleep

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_API_BASE = "https://slack.com/api"


class SlackClient:
    """Minimal Slack API client using xoxc- token + cookie auth."""

    def __init__(self, token, cookie):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Cookie": f"d={cookie}",
        })

    def _api_call(self, method, **kwargs):
        """Make a Slack API call with automatic rate limit handling."""
        while True:
            response = self.session.post(f"{SLACK_API_BASE}/{method}", data=kwargs)
            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                if error == "ratelimited":
                    retry_after = int(response.headers.get("Retry-After", 10))
                    print(f"  Rate limited. Sleeping {retry_after}s...")
                    sleep(retry_after)
                    continue
                raise Exception(f"Slack API error ({method}): {error}")

            return data

    def auth_test(self):
        return self._api_call("auth.test")

    def get_users(self):
        """Fetch all users in the workspace."""
        users = []
        cursor = None
        while True:
            kwargs = {"limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            data = self._api_call("users.list", **kwargs)
            users.extend(data.get("members", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            sleep(1)
        return users

    def get_conversations(self, types="im,mpim,private_channel"):
        """Fetch conversations of given types."""
        conversations = []
        cursor = None
        while True:
            kwargs = {"types": types, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            data = self._api_call("conversations.list", **kwargs)
            conversations.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            sleep(1)
        return conversations

    def get_history(self, channel_id, oldest=0, latest=None, page_size=200):
        """Fetch complete message history for a conversation."""
        messages = []
        cursor = None
        while True:
            kwargs = {
                "channel": channel_id,
                "limit": page_size,
                "oldest": oldest,
            }
            if latest:
                kwargs["latest"] = latest
            if cursor:
                kwargs["cursor"] = cursor

            data = self._api_call("conversations.history", **kwargs)
            messages.extend(data.get("messages", []))

            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not data.get("has_more") or not cursor:
                break
            sleep(1)

        messages.sort(key=lambda m: m["ts"])
        return messages

    def get_conversation_members(self, channel_id):
        """Fetch members of a conversation."""
        members = []
        cursor = None
        while True:
            kwargs = {"channel": channel_id, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            data = self._api_call("conversations.members", **kwargs)
            members.extend(data.get("members", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            sleep(1)
        return members


def parse_timestamp(ts):
    """Create datetime from Slack timestamp string."""
    if "." in ts:
        return datetime.utcfromtimestamp(float(ts.split(".")[0]))
    return datetime.utcfromtimestamp(float(ts))


def date_to_ts(date_str):
    """Convert YYYY-MM-DD to Unix timestamp."""
    return str(int(datetime.strptime(date_str, "%Y-%m-%d").timestamp()))


def mkdir(directory):
    os.makedirs(directory, exist_ok=True)


def write_message_file(filename, messages):
    """Write messages to a JSON file."""
    if not messages:
        return
    mkdir(os.path.dirname(filename))
    with open(filename, "w") as f:
        json.dump(messages, f, indent=4)


def parse_messages(room_dir, messages):
    """Split messages by date and write to separate JSON files."""
    current_date = ""
    current_messages = []

    for message in messages:
        ts = parse_timestamp(message["ts"])
        file_date = ts.strftime("%Y-%m-%d")

        if file_date != current_date:
            if current_messages:
                out_file = os.path.join(room_dir, f"{current_date}.json")
                write_message_file(out_file, current_messages)
            current_date = file_date
            current_messages = []

        current_messages.append(message)

    if current_messages:
        out_file = os.path.join(room_dir, f"{current_date}.json")
        write_message_file(out_file, current_messages)


def get_conversation_name(conv, user_names_by_id):
    """Get a human-readable name for a conversation."""
    if conv.get("is_im"):
        user_id = conv.get("user", "unknown")
        user_name = user_names_by_id.get(user_id, user_id)
        return f"dm--{user_name}"
    elif conv.get("is_mpim"):
        return conv.get("name", conv["id"])
    else:
        return conv.get("name", conv["id"])


def main():
    parser = argparse.ArgumentParser(
        description="Export Slack DMs, Group DMs, and Private Channels (data not available via admin export)"
    )
    parser.add_argument(
        "--token",
        default=os.getenv("SLACK_TOKEN"),
        help="Slack xoxc- token (or set SLACK_TOKEN in .env)",
    )
    parser.add_argument(
        "--cookie",
        default=os.getenv("SLACK_COOKIE"),
        help="Slack d= cookie value (or set SLACK_COOKIE in .env)",
    )
    parser.add_argument(
        "--oldest",
        default=None,
        metavar="YYYY-MM-DD",
        help="Only export messages after this date (e.g. 2025-01-01)",
    )
    parser.add_argument(
        "--latest",
        default=None,
        metavar="YYYY-MM-DD",
        help="Only export messages before this date (e.g. 2026-03-10)",
    )
    parser.add_argument(
        "--zip",
        default=None,
        metavar="FILENAME",
        help="Output as a zip file (without .zip extension)",
    )
    parser.add_argument(
        "--types",
        default="im,mpim,private_channel",
        help="Conversation types to export (default: im,mpim,private_channel)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List conversations that would be exported without fetching messages",
    )

    args = parser.parse_args()

    if not args.token:
        parser.error("--token is required (or set SLACK_TOKEN in .env)")
    if not args.cookie:
        parser.error("--cookie is required (or set SLACK_COOKIE in .env)")

    # Convert dates to timestamps
    oldest = date_to_ts(args.oldest) if args.oldest else "0"
    latest = date_to_ts(args.latest) if args.latest else None

    # Init client
    slack = SlackClient(args.token, args.cookie)

    # Test auth
    auth = slack.auth_test()
    print(f"Authenticated as {auth['user']} in team {auth['team']}")
    token_owner_id = auth["user_id"]

    # Fetch users
    print("Fetching users...")
    users = slack.get_users()
    user_names_by_id = {u["id"]: u["name"] for u in users}
    print(f"  Found {len(users)} users")

    # Fetch conversations
    print(f"Fetching conversations (types: {args.types})...")
    conversations = slack.get_conversations(types=args.types)

    # Categorize
    ims = [c for c in conversations if c.get("is_im")]
    mpims = [c for c in conversations if c.get("is_mpim")]
    private_channels = [c for c in conversations if c.get("is_private") and not c.get("is_mpim") and not c.get("is_im")]

    print(f"  Found {len(ims)} DMs")
    print(f"  Found {len(mpims)} Group DMs")
    print(f"  Found {len(private_channels)} Private Channels")
    print(f"  Total: {len(conversations)} conversations")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print("\n1:1 DMs:")
        for c in ims:
            print(f"  {user_names_by_id.get(c.get('user', ''), c['id'])}")
        print("\nGroup DMs:")
        for c in mpims:
            print(f"  {c.get('name', c['id'])}")
        print("\nPrivate Channels:")
        for c in private_channels:
            print(f"  {c.get('name', c['id'])}")
        return

    # Setup output directory
    date_range = ""
    if args.oldest:
        date_range = f"_from_{args.oldest}"
    if args.latest:
        date_range += f"_to_{args.latest}"

    output_dir = f"{datetime.today().strftime('%Y%m%d-%H%M%S')}-slack_export{date_range}"
    mkdir(output_dir)
    os.chdir(output_dir)

    # Dump metadata files
    print("\nWriting metadata files...")

    # Add members to DMs for slack-export-viewer compatibility
    for dm in ims:
        dm["members"] = [dm.get("user", ""), token_owner_id]

    with open("users.json", "w") as f:
        json.dump(users, f, indent=4)
    with open("dms.json", "w") as f:
        json.dump(ims, f, indent=4)
    with open("mpims.json", "w") as f:
        json.dump(mpims, f, indent=4)
    with open("groups.json", "w") as f:
        json.dump(private_channels, f, indent=4)
    with open("channels.json", "w") as f:
        json.dump([], f, indent=4)  # empty, we skip public channels

    # Export conversations
    total = len(conversations)
    for i, conv in enumerate(conversations, 1):
        name = get_conversation_name(conv, user_names_by_id)
        conv_type = "DM" if conv.get("is_im") else "Group DM" if conv.get("is_mpim") else "Private Channel"

        print(f"[{i}/{total}] Fetching {conv_type}: {name}")

        try:
            messages = slack.get_history(conv["id"], oldest=oldest, latest=latest)
            print(f"  -> {len(messages)} messages")

            if messages:
                parse_messages(name, messages)
        except Exception as e:
            print(f"  -> ERROR: {e}")
            continue

    # Finalize
    os.chdir("..")

    if args.zip:
        zip_name = args.zip
        print(f"\nCreating {zip_name}.zip...")
        shutil.make_archive(zip_name, "zip", output_dir)
        shutil.rmtree(output_dir)
        print(f"Done! Export saved to {zip_name}.zip")
    else:
        print(f"\nDone! Export saved to {output_dir}/")


if __name__ == "__main__":
    main()
