"""Run Khyati on Email and WhatsApp through one Caspian handler."""

from config import get_settings
from reply_agent import ReplyAgent


def build_handler(reply_agent: ReplyAgent):
    """Build the single normalized handler shared by every Caspian channel."""

    def handle(message) -> None:
        text = (message.text or "").strip()
        sender = (message.sender or {}).get("address", "unknown")
        print(f"<- [{message.channel}] {sender}: {text}")

        if not text:
            message.reply("I received your message, but it did not include any text.")
            return

        try:
            reply = reply_agent.respond(text=text, channel=message.channel)
        except Exception:
            message.reply(
                "I'm sorry, I couldn't process that just now. Please try again shortly."
            )
            return

        message.reply(reply)
        print(f"-> [{message.channel}] {reply}")

    return handle


def main() -> None:
    settings = get_settings()
    if not settings.caspian_api_key:
        raise RuntimeError("Set CASPIAN_API_KEY in .env before running channels.py")
    if not settings.llm_api_key:
        raise RuntimeError("Set the selected provider's API key in .env")

    from caspian_sdk import CommClient

    client = CommClient(
        api_key=settings.caspian_api_key,
        base_url=settings.caspian_base_url,
    )
    email = client.connect_email(username=settings.caspian_email_username)
    whatsapp = client.connect_whatsapp(
        provider=settings.caspian_whatsapp_provider
    )
    reply_agent = ReplyAgent(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        behavior_prompt=client.behavior_prompt(),
    )

    print(f"Email active: {email.get('address', email.get('id'))}")
    print(f"WhatsApp active: {whatsapp.get('address', whatsapp.get('id'))}")
    print("Khyati is listening on both channels. Press Ctrl+C to stop.")

    client.on_message(build_handler(reply_agent))
    client.listen()


if __name__ == "__main__":
    main()
