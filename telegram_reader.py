import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import User, Chat, Channel
import anthropic

load_dotenv()

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.environ.get("TELEGRAM_PHONE", "")

CHATS_TO_SHOW = 10
MESSAGES_PER_CHAT = 5


def format_sender(sender) -> str:
    if isinstance(sender, User):
        name = " ".join(filter(None, [sender.first_name, sender.last_name]))
        return name or sender.username or "Unknown"
    return getattr(sender, "title", "Unknown")


async def get_recent_chats(client: TelegramClient) -> list:
    dialogs = await client.get_dialogs(limit=CHATS_TO_SHOW)
    return dialogs


async def get_messages(client: TelegramClient, dialog) -> list[dict]:
    messages = []
    async for msg in client.iter_messages(dialog.entity, limit=MESSAGES_PER_CHAT):
        if msg.text:
            sender_name = "Unknown"
            if msg.sender:
                sender_name = format_sender(msg.sender)
            messages.append({
                "sender": sender_name,
                "text": msg.text,
                "date": msg.date.strftime("%Y-%m-%d %H:%M"),
            })
    return messages


def summarize_messages(chat_name: str, messages: list[dict]) -> str:
    if not messages:
        return "No messages to summarize."

    anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    conversation_text = "\n".join(
        f"[{m['date']}] {m['sender']}: {m['text']}" for m in messages
    )

    prompt = (
        f"Here are the latest messages from the Telegram chat \"{chat_name}\":\n\n"
        f"{conversation_text}\n\n"
        "Please provide a brief 2–3 sentence summary of what this conversation is about."
    )

    with anthropic_client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=512,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        summary = ""
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                summary += event.delta.text
        return summary.strip()


async def main():
    print("Connecting to Telegram...\n")
    async with TelegramClient("session", API_ID, API_HASH) as client:
        await client.start(phone=PHONE if PHONE else None)
        print("Connected!\n")

        print(f"=== Recent {CHATS_TO_SHOW} Chats ===\n")
        dialogs = await get_recent_chats(client)

        for i, dialog in enumerate(dialogs, 1):
            entity = dialog.entity
            if isinstance(entity, User):
                chat_type = "DM"
                name = " ".join(filter(None, [entity.first_name, entity.last_name])) or entity.username or "Unknown"
            elif isinstance(entity, Channel):
                chat_type = "Channel" if entity.broadcast else "Group"
                name = entity.title
            else:
                chat_type = "Chat"
                name = getattr(entity, "title", "Unknown")

            unread = dialog.unread_count
            print(f"{i:2}. [{chat_type}] {name}  (unread: {unread})")

        print("\n=== Latest Messages & Summaries ===\n")
        for dialog in dialogs[:5]:
            entity = dialog.entity
            if isinstance(entity, User):
                name = " ".join(filter(None, [entity.first_name, entity.last_name])) or entity.username or "Unknown"
            else:
                name = getattr(entity, "title", "Unknown")

            print(f"--- {name} ---")
            messages = await get_messages(client, dialog)

            if not messages:
                print("  (no text messages found)\n")
                continue

            for msg in messages:
                print(f"  [{msg['date']}] {msg['sender']}: {msg['text'][:120]}")

            if os.environ.get("ANTHROPIC_API_KEY"):
                print("\n  Summary:")
                summary = summarize_messages(name, messages)
                print(f"  {summary}")
            else:
                print("\n  (set ANTHROPIC_API_KEY in .env to enable summaries)")
            print()


if __name__ == "__main__":
    asyncio.run(main())
