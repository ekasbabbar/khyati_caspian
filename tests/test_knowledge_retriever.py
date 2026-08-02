"""Tests for chunking, relevance, persistence, and audience filtering."""
from pathlib import Path
import tempfile
import unittest

from knowledge_retriever import KnowledgeRetriever


class KnowledgeRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "knowledge"
        self.root.mkdir()
        (self.root / "skills.md").write_text(
            "# Data Science\nPython, SQL, statistics, visualization and data cleaning.\n\n"
            "# Backend\nFastAPI and REST APIs.", encoding="utf-8"
        )
        (self.root / "private.md").write_text(
            "---\nvisibility: owner_only\napproval_required: true\n---\n"
            "# Private target\nMinimum compensation target is private.", encoding="utf-8"
        )
        self.index = Path(self.temp.name) / "index.sqlite3"

    def tearDown(self): self.temp.cleanup()

    def test_role_language_retrieves_transferable_skills(self):
        result = KnowledgeRetriever(self.root, self.index).search("data analyst intern")
        self.assertIn("skills.md#Data Science", result.sources)
        self.assertIn("Python, SQL", result.context)

    def test_greeting_retrieves_no_knowledge(self):
        result = KnowledgeRetriever(self.root, self.index).search("hey")
        self.assertEqual(result.sources, ())

    def test_unrelated_work_request_retrieves_no_knowledge(self):
        result = KnowledgeRetriever(self.root, self.index).search(
            "solve this poker algorithm"
        )
        self.assertEqual(result.sources, ())

    def test_recruiter_cannot_retrieve_owner_only_chunk(self):
        retriever = KnowledgeRetriever(self.root, self.index)
        result = retriever.search("minimum compensation target", audience="recruiter")
        self.assertNotIn("private.md", result.context)

    def test_owner_can_retrieve_owner_only_chunk(self):
        retriever = KnowledgeRetriever(self.root, self.index)
        result = retriever.search("minimum compensation target", audience="owner")
        self.assertIn("private.md#Private target", result.sources)
        self.assertIn("APPROVAL REQUIRED: yes", result.context)

    def test_index_refreshes_when_source_changes(self):
        first = KnowledgeRetriever(self.root, self.index)
        initial_count = first.chunk_count
        (self.root / "project.md").write_text("# Project\nBuilt a retrieval agent.", encoding="utf-8")
        second = KnowledgeRetriever(self.root, self.index)
        self.assertGreater(second.chunk_count, initial_count)

    def test_multi_question_retrieval_preserves_each_topic(self):
        retriever = KnowledgeRetriever(self.root, self.index)
        result = retriever.search_many(
            ["What data science skills does the candidate have?", "What backend work has the candidate done?"]
        )
        self.assertIn("skills.md#Data Science", result.sources)
        self.assertIn("skills.md#Backend", result.sources)


if __name__ == "__main__": unittest.main()
