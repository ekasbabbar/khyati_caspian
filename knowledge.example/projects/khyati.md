# Khyati

Khyati is a grounded personal career representative built for the Caspian AI
Agent Hackathon. Recruiters email Khyati to ask about the candidate's verified
experience and projects. Telegram is used for private candidate coordination.

Technical details:

- Python and Pydantic
- Gemini through an OpenAI-compatible interface
- Caspian Email and Telegram through one normalized handler
- Bounded conversation memory isolated by conversation ID
- Deterministic fallbacks and bounded model concurrency

Do not claim that Khyati autonomously schedules interviews or negotiates offers.
