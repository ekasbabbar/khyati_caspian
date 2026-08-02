"""Resilient ordered LLM provider chain with basic circuit breaking."""

from dataclasses import dataclass, field
import logging
from threading import Lock
from time import monotonic
from types import SimpleNamespace

logger = logging.getLogger(__name__)


@dataclass
class ProviderEndpoint:
    name: str
    model: str
    client: object
    request_options: dict = field(default_factory=dict)
    failures: int = 0
    circuit_open_until: float = 0.0


class ProviderChainError(RuntimeError):
    pass


class ProviderChain:
    """Expose an OpenAI-like chat client while failing over in order."""

    def __init__(
        self,
        endpoints: list[ProviderEndpoint],
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> None:
        if not endpoints:
            raise ValueError("At least one LLM endpoint is required")
        self._endpoints = endpoints
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._lock = Lock()
        self.last_provider: str | None = None
        self.chat = SimpleNamespace(completions=self)

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(endpoint.name for endpoint in self._endpoints)

    def create(self, **kwargs):
        return self.create_validated(lambda response: response, **kwargs)

    def create_validated(self, validator, **kwargs):
        """Fail over when transport succeeds but response validation fails."""
        errors: list[str] = []
        now = monotonic()
        for endpoint in self._endpoints:
            with self._lock:
                if endpoint.circuit_open_until > now:
                    errors.append(f"{endpoint.name}: circuit open")
                    continue
            request = dict(kwargs)
            request["model"] = endpoint.model
            request.update(endpoint.request_options)
            try:
                response = endpoint.client.chat.completions.create(**request)
                validated = validator(response)
            except Exception as error:
                with self._lock:
                    endpoint.failures += 1
                    if endpoint.failures >= self._failure_threshold:
                        endpoint.circuit_open_until = monotonic() + self._cooldown_seconds
                errors.append(f"{endpoint.name}: {type(error).__name__}: {error}")
                logger.warning("LLM provider %s failed; trying fallback: %s", endpoint.name, error)
                continue
            with self._lock:
                endpoint.failures = 0
                endpoint.circuit_open_until = 0.0
                self.last_provider = endpoint.name
            return validated
        raise ProviderChainError("All LLM providers failed (" + "; ".join(errors) + ")")


def build_provider_chain(settings) -> ProviderChain:
    """Construct configured OpenAI-compatible clients in primary-first order."""
    from openai import OpenAI

    endpoints: list[ProviderEndpoint] = []
    configurations = (
        (
            "featherless",
            settings.featherless_api_key,
            settings.featherless_model,
            settings.featherless_base_url,
            settings.featherless_timeout_seconds,
        ),
        (
            "gemini",
            settings.gemini_api_key,
            settings.gemini_model,
            settings.gemini_base_url,
            settings.gemini_timeout_seconds,
        ),
    )
    for name, api_key, model, base_url, timeout in configurations:
        if not api_key:
            continue
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )
        request_options = (
            {
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            }
            if name == "featherless" and "qwen3" in model.lower()
            else {}
        )
        endpoints.append(ProviderEndpoint(name, model, client, request_options))
    if not endpoints:
        raise RuntimeError("Configure FEATHERLESS_API_KEY or GEMINI_API_KEY")
    return ProviderChain(
        endpoints,
        failure_threshold=settings.llm_circuit_failure_threshold,
        cooldown_seconds=settings.llm_circuit_cooldown_seconds,
    )
