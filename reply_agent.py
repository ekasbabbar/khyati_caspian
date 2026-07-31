"""Generate helpful replies for inbound Caspian conversations."""

REPLY_SYSTEM_PROMPT = """\
You are Khyati, a customer-success agent.

Respond helpfully, honestly, and concisely. Optimize for the customer's success
and long-term trust, never pressure them into a sale. Do not claim to have taken
an action you cannot verify. Ask one clear follow-up question when more context
is needed. Return only the message to send.
"""


class ReplyAgent:
    """Create channel-aware responses to inbound customer messages."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        behavior_prompt: str = "",
        client: object | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=1,
            )
        self._client = client
        self._model = model
        self._system_prompt = REPLY_SYSTEM_PROMPT
        if behavior_prompt:
            self._system_prompt += f"\n\n{behavior_prompt}"

    def respond(self, text: str, channel: str) -> str:
        """Generate one reply using the same logic for every channel."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": f"Channel: {channel}\nCustomer message: {text}",
                },
            ],
        )
        reply = (response.choices[0].message.content or "").strip()
        if not reply:
            raise ValueError("OpenAI returned an empty reply")
        return reply
