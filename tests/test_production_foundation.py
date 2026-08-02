"""Contracts for the channel-independent core and knowledge source boundary."""

from pathlib import Path
import tempfile
import unittest

from conversation_memory import ConversationMemory
from khyati import KhyatiService
from khyati.knowledge.sources import LocalKnowledgeSource, validate_document
from khyati.knowledge.sources import S3KnowledgeSource


class StubGenerator:
    def __init__(self):
        self.calls = []

    def respond(self, text, channel, history=None):
        self.calls.append((text, channel, history or []))
        return "Grounded answer"


class KhyatiServiceTests(unittest.TestCase):
    def test_portfolio_and_caspian_share_one_contract(self):
        generator = StubGenerator()
        service = KhyatiService(generator, ConversationMemory())
        response = service.respond(
            text="What has Ekas built?",
            audience="recruiter",
            conversation_id="web-1",
            source="portfolio",
        )
        self.assertEqual(response.answer, "Grounded answer")
        self.assertEqual(generator.calls[0][1], "portfolio")

    def test_authenticated_owner_maps_to_private_role(self):
        generator = StubGenerator()
        service = KhyatiService(generator)
        service.respond(
            text="Show my pending requests",
            audience="owner",
            conversation_id="tg-owner",
            source="telegram",
        )
        self.assertEqual(generator.calls[0][1], "owner")

    def test_history_is_shared_through_service_boundary(self):
        generator = StubGenerator()
        service = KhyatiService(generator)
        for text in ("First", "Second"):
            service.respond(
                text=text,
                audience="recruiter",
                conversation_id="thread",
                source="email",
            )
        self.assertEqual(generator.calls[1][2][0]["content"], "First")


class KnowledgeSourceTests(unittest.TestCase):
    VALID = """---
visibility: recruiter
approval_required: false
document_type: profile
topics: candidate, background
description: Verified candidate profile
last_updated: 2026-08-02
---
# Profile
Verified facts.
"""

    def test_local_source_validates_and_materializes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "profile.md").write_text(self.VALID, encoding="utf-8")
            self.assertEqual(LocalKnowledgeSource(root).materialize(), root)

    def test_missing_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_document("bad.md", "---\nvisibility: public\n---\n# Bad\n")

    def test_private_s3_release_is_verified_and_materialized(self):
        import hashlib
        import json
        from io import BytesIO

        document = self.VALID.encode()
        manifest = json.dumps({
            "version": "commit-123",
            "documents": [{
                "path": "profile.md",
                "key": "releases/commit-123/profile.md",
                "sha256": hashlib.sha256(document).hexdigest(),
            }],
        }).encode()

        class FakeS3:
            def get_object(self, Bucket, Key):
                values = {
                    "current/manifest.json": manifest,
                    "releases/commit-123/profile.md": document,
                }
                return {"Body": BytesIO(values[Key])}

        with tempfile.TemporaryDirectory() as directory:
            source = S3KnowledgeSource(
                "private-bucket", "current/manifest.json",
                Path(directory), client=FakeS3(),
            )
            result = source.materialize()
            self.assertEqual((result / "profile.md").read_text(), self.VALID)


if __name__ == "__main__":
    unittest.main()
