"""Run Khyati on Email and Telegram through one Caspian handler."""

from config import get_settings
from conversation_memory import ConversationMemory
from knowledge_retriever import KnowledgeRetriever
from reply_agent import ReplyAgent


def explain_connection_error(channel: str, error: Exception) -> str:
    """Turn common Caspian failures into actionable startup guidance."""
    error_name = type(error).__name__
    if error_name == "AccountRequiredError":
        return f"{channel}: Caspian login required. Run `caspian login`."
    if error_name == "InsufficientCreditError":
        return (
            f"{channel}: insufficient Caspian credit. Add credit or request "
            "hackathon starter credit."
        )
    return f"{channel}: connection failed ({error})."


def connect_available_channels(client, settings) -> dict[str, dict]:
    """Connect each channel independently so one failure does not stop the other."""
    connected: dict[str, dict] = {}

    try:
        connected["email"] = client.connect_email(
            username=settings.caspian_email_username
        )
    except Exception as error:
        print(f"WARNING: {explain_connection_error('Email', error)}")

    if not settings.caspian_telegram_bot_token:
        print("WARNING: Telegram: set TELEGRAM_BOT_TOKEN in .env.")
    else:
        try:
            connected["telegram"] = client.connect_telegram(
                bot_token=settings.caspian_telegram_bot_token
            )
        except Exception as error:
            print(f"WARNING: {explain_connection_error('Telegram', error)}")

    if not connected:
        raise RuntimeError(
            "Khyati could not connect Email or Telegram. Fix at least one "
            "connection and try again."
        )
    return connected


def build_handler(
    reply_agent: ReplyAgent,
    memory: ConversationMemory | None = None,
    client=None,
    owner_telegram_username: str | None = None,
):
    """Build the single normalized handler shared by every Caspian channel."""
    memory = memory or ConversationMemory()
    owner_conversation_id: str | None = None
    expected_owner = (owner_telegram_username or "").strip().lower().lstrip("@")

    def handle(message) -> None:
        nonlocal owner_conversation_id
        text = (message.text or "").strip()
        conversation_id = message.conversation_id
        sender = (message.sender or {}).get("address", "unknown")
        print(f"<- [{message.channel}] {sender}: {text}")

        if message.channel == "telegram":
            actual_sender = sender.strip().lower().lstrip("@")
            if expected_owner and actual_sender != expected_owner:
                message.reply("This is a private career-agent channel.")
                return
            owner_conversation_id = conversation_id

        if not text:
            message.reply("I received your message, but it did not include any text.")
            return

        try:
            reply = reply_agent.respond(
                text=text,
                channel=message.channel,
                history=memory.history(conversation_id),
            )
        except Exception as error:
            print(f"WARNING: reply generation failed ({error}).")
            fallback = (
                "Thanks for reaching out. I'm having trouble generating a full "
                "response right now, but your message has been received. Please "
                "try again shortly."
            )
            message.reply(fallback)
            memory.add(conversation_id, "user", text)
            memory.add(conversation_id, "assistant", fallback)
            return

        message.reply(reply)
        memory.add(conversation_id, "user", text)
        memory.add(conversation_id, "assistant", reply)
        print(f"-> [{message.channel}] {reply}")

        if message.channel == "email" and client and owner_conversation_id:
            try:
                client.send_message(
                    owner_conversation_id,
                    text=(
                        f"Recruiter message from {sender}:\n\n{text}\n\n"
                        "Khyati replied:\n\n"
                        f"{reply}"
                    ),
                )
            except Exception as error:
                print(f"WARNING: owner notification failed ({error}).")

    return handle


def main() -> None:
    settings = get_settings()
    if not settings.caspian_api_key:
        raise RuntimeError("Set CASPIAN_API_KEY in .env before running channels.py")
    if not settings.llm_api_key:
        raise RuntimeError("Set the selected provider's API key in .env")
    if not settings.owner_telegram_username:
        raise RuntimeError(
            "Set KHYATI_OWNER_TELEGRAM_USERNAME in .env to secure Telegram."
        )

    from caspian_sdk import CommClient

    client = CommClient(
        api_key=settings.caspian_api_key,
        base_url=settings.caspian_base_url,
    )
    connected = connect_available_channels(client, settings)
    retriever = KnowledgeRetriever(
        settings.knowledge_dir,
        settings.knowledge_index_path,
    )
    print(
        f"Career knowledge indexed: {retriever.chunk_count} chunks from "
        f"{retriever.source_count} files at {settings.knowledge_dir.resolve()}"
    )

    try:
        behavior_prompt = client.behavior_prompt()
    except Exception as error:
        print(
            f"WARNING: channel behavior guide unavailable ({error}); "
            "using Khyati's base reply policy."
        )
        behavior_prompt = ""

    reply_agent = ReplyAgent(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_concurrent=settings.llm_max_concurrent,
        behavior_prompt=behavior_prompt,
        retriever=retriever,
    )

    for channel, connection in connected.items():
        address = connection.get("address", connection.get("id", "active"))
        print(f"{channel.title()} active: {address}")
    unavailable = {"email", "telegram"} - connected.keys()
    if unavailable:
        print(f"Degraded mode: unavailable channel(s): {', '.join(sorted(unavailable))}")
    print("Khyati is listening. Press Ctrl+C to stop.")

    client.on_message(
        build_handler(
            reply_agent,
            client=client,
            owner_telegram_username=settings.owner_telegram_username,
        )
    )
    try:
        client.listen()
    except KeyboardInterrupt:
        print("\nKhyati stopped.")
    except Exception as error:
        raise RuntimeError(f"Caspian listener stopped unexpectedly: {error}") from error
    finally:
        client.close()


if __name__ == "__main__":
    main()
