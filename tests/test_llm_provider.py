"""Offline tests for ordered LLM failover and circuit breaking."""
from types import SimpleNamespace
import unittest

from llm_provider import ProviderChain, ProviderEndpoint


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response=response; self.error=error; self.calls=[]
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error: raise self.error
        return self.response


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class ProviderChainTests(unittest.TestCase):
    def test_primary_is_used_when_healthy(self):
        expected=object(); primary=FakeCompletions(response=expected); secondary=FakeCompletions(response=object())
        chain=ProviderChain([ProviderEndpoint("featherless","qwen",fake_client(primary)),ProviderEndpoint("gemini","flash",fake_client(secondary))])
        self.assertIs(chain.create(model="ignored",messages=[]),expected)
        self.assertEqual(chain.last_provider,"featherless"); self.assertEqual(len(secondary.calls),0)
        self.assertEqual(primary.calls[0]["model"],"qwen")

    def test_secondary_is_used_after_primary_timeout(self):
        primary=FakeCompletions(error=TimeoutError("slow")); expected=object(); secondary=FakeCompletions(response=expected)
        chain=ProviderChain([ProviderEndpoint("featherless","qwen",fake_client(primary)),ProviderEndpoint("gemini","flash",fake_client(secondary))])
        self.assertIs(chain.create(model="ignored",messages=[]),expected)
        self.assertEqual(chain.last_provider,"gemini"); self.assertEqual(secondary.calls[0]["model"],"flash")

    def test_circuit_skips_repeatedly_failing_primary(self):
        primary=FakeCompletions(error=TimeoutError("slow")); secondary=FakeCompletions(response=object())
        chain=ProviderChain([ProviderEndpoint("featherless","qwen",fake_client(primary)),ProviderEndpoint("gemini","flash",fake_client(secondary))],failure_threshold=1,cooldown_seconds=60)
        chain.create(model="ignored",messages=[]); chain.create(model="ignored",messages=[])
        self.assertEqual(len(primary.calls),1); self.assertEqual(len(secondary.calls),2)

    def test_validation_failure_uses_secondary(self):
        primary=FakeCompletions(response="bad"); secondary=FakeCompletions(response="good")
        chain=ProviderChain([ProviderEndpoint("featherless","qwen",fake_client(primary)),ProviderEndpoint("gemini","flash",fake_client(secondary))])
        result=chain.create_validated(
            lambda response: response if response == "good" else (_ for _ in ()).throw(ValueError("invalid JSON")),
            model="ignored",messages=[]
        )
        self.assertEqual(result,"good"); self.assertEqual(chain.last_provider,"gemini")

    def test_provider_specific_request_options_are_applied(self):
        completions=FakeCompletions(response=object())
        options={"extra_body":{"chat_template_kwargs":{"enable_thinking":False}}}
        chain=ProviderChain([ProviderEndpoint("featherless","qwen",fake_client(completions),options)])
        chain.create(model="ignored",messages=[])
        self.assertEqual(completions.calls[0]["extra_body"],options["extra_body"])


if __name__ == "__main__": unittest.main()
