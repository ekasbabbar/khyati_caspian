"""Persistent, privacy-aware hybrid retrieval for career knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
STOPWORDS = {
    "a", "about", "am", "an", "and", "are", "as", "at", "be", "can",
    "could", "do", "does", "for", "from", "he", "her", "him", "his",
    "i", "in", "is", "it", "me", "of", "on", "or", "please", "she",
    "tell", "that", "the", "their", "them", "they", "this", "to", "us",
    "was", "what", "when", "where", "which", "who", "why", "with", "would",
    "you", "your",
}
NO_RETRIEVAL_MESSAGES = {
    "hello", "hi", "hey", "thanks", "thank you", "okay", "ok", "cool",
    "good morning", "good afternoon", "good evening", "bye", "goodbye",
}
UNRELATED_TASK_TERMS = {
    "solve", "solution", "homework", "assignment", "leetcode", "algorithm",
    "debug", "translate", "essay", "recipe", "poker", "array",
}
CAREER_CONTEXT_TERMS = {
    "candidate", "ekas", "recruiter", "role", "job", "intern", "internship",
    "experience", "skill", "skills", "project", "resume", "cv", "hire",
    "hiring", "fit", "qualified", "qualification", "background",
}

# Small domain vocabulary bridges recruiter language and resume terminology.
# This is deterministic, inspectable, and complements exact keyword ranking.
CONCEPTS: dict[str, tuple[str, ...]] = {
    "data analyst": ("data", "analytics", "sql", "python", "statistics", "visualization", "eda"),
    "data analysis": ("analytics", "sql", "python", "statistics", "visualization", "eda"),
    "analytics": ("data", "sql", "python", "statistics", "visualization", "eda"),
    "product manager": ("product", "leadership", "communication", "ownership", "planning", "users"),
    "product management": ("product", "leadership", "communication", "ownership", "planning", "users"),
    "pm intern": ("product", "leadership", "communication", "ownership", "planning"),
    "backend": ("api", "fastapi", "database", "sql", "server", "python"),
    "machine learning": ("ml", "pytorch", "scikit-learn", "models", "data", "ai"),
    "artificial intelligence": ("ai", "machine learning", "llm", "agents", "models"),
    "ai agent": ("agents", "agentic", "llm", "rag", "retrieval", "caspian", "gemini", "automation"),
    "ai agents": ("agent", "agentic", "llm", "rag", "retrieval", "caspian", "gemini", "automation"),
    "software engineer": ("programming", "backend", "frontend", "api", "git", "projects"),
    "algorithm": ("algorithms", "c++", "data structures", "competitive programming", "problem solving"),
    "algorithms": ("algorithm", "c++", "data structures", "competitive programming", "problem solving"),
    "availability": ("start", "summer", "remote", "relocate", "internship", "schedule"),
    "compensation": ("salary", "pay", "stipend", "offer", "negotiate"),
    "background": ("profile", "education", "experience", "skills", "projects"),
    "candidate": ("profile", "education", "experience", "skills", "projects"),
    "resume": ("profile", "education", "experience", "skills", "projects"),
    "who is": ("profile", "biography", "identity", "education", "experience"),
    "tell me about": ("profile", "biography", "identity", "experience", "projects"),
    "academic": ("education", "degree", "major", "university", "coursework"),
    "education": ("degree", "major", "university", "coursework", "academic"),
}

TOKEN_ALIASES = {
    "analyst": "analytics", "analyses": "analytics", "analysis": "analytics",
    "developed": "build", "developer": "build", "built": "build",
    "collaborated": "collaboration", "collaborating": "collaboration",
    "engineer": "engineering", "engineers": "engineering",
    "interns": "internship", "internships": "internship",
    "managed": "management", "manager": "management",
    "projects": "project", "skills": "skill", "technologies": "technology",
}


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    source: str
    heading: str
    text: str
    visibility: str = "recruiter"
    approval_required: bool = False
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalResult:
    context: str
    sources: tuple[str, ...]
    chunks: tuple[KnowledgeChunk, ...]


def _tokens(text: str) -> list[str]:
    return [TOKEN_ALIASES.get(token, token) for token in TOKEN_PATTERN.findall(text.lower())]


def _query_phrases(tokens: list[str]) -> tuple[tuple[str, ...], ...]:
    """Return meaningful bigrams/trigrams for exact and proximity ranking."""
    meaningful = [token for token in tokens if token not in STOPWORDS]
    return tuple(
        tuple(meaningful[index:index + size])
        for size in (3, 2)
        for index in range(len(meaningful) - size + 1)
    )


def _minimum_window(document: list[str], terms: set[str]) -> int | None:
    """Smallest token window containing all matched query terms."""
    required = terms & set(document)
    if len(required) < 2:
        return None
    counts: dict[str, int] = {}
    left = 0
    best: int | None = None
    for right, token in enumerate(document):
        if token in required:
            counts[token] = counts.get(token, 0) + 1
        while len(counts) == len(required):
            best = min(best or len(document), right - left + 1)
            left_token = document[left]
            if left_token in counts:
                counts[left_token] -= 1
                if counts[left_token] == 0:
                    del counts[left_token]
            left += 1
    return best


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the small YAML-like metadata subset used by knowledge files."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip().strip('"\'')
    return metadata, text[end + 5 :]


def _split_markdown(source: str, text: str, max_chars: int = 2_000) -> list[KnowledgeChunk]:
    metadata, body = _frontmatter(text)
    visibility = metadata.get("visibility", "recruiter").lower()
    if visibility not in {"public", "recruiter", "owner_only"}:
        raise ValueError(f"Invalid visibility '{visibility}' in {source}")
    approval = metadata.get("approval_required", "false").lower() in {"1", "true", "yes"}
    topic_values = [part.strip().lower() for part in metadata.get("topics", "").split(",") if part.strip()]
    # These descriptive fields also participate in ranking without being sent
    # as claims to the model.
    topic_values.extend(
        value.lower() for key in ("document_type", "description")
        if (value := metadata.get(key))
    )
    topics = tuple(topic_values)

    sections: list[tuple[str, list[str]]] = []
    heading = Path(source).stem.replace("_", " ").title()
    lines: list[str] = []
    for line in body.splitlines():
        match = HEADING_PATTERN.match(line)
        if match and lines:
            sections.append((heading, lines))
            heading, lines = match.group(2).strip(), []
        elif match:
            heading = match.group(2).strip()
        else:
            lines.append(line)
    if lines:
        sections.append((heading, lines))

    chunks: list[KnowledgeChunk] = []
    for section_heading, section_lines in sections:
        content = "\n".join(section_lines).strip()
        if not content:
            continue
        paragraphs = re.split(r"\n\s*\n", content)
        current = ""
        parts: list[str] = []
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip()
            if current and len(candidate) > max_chars:
                parts.append(current)
                current = paragraph
            else:
                current = candidate
        if current:
            parts.append(current)
        for index, part in enumerate(parts):
            chunk_id = hashlib.sha256(f"{source}:{section_heading}:{index}:{part}".encode()).hexdigest()
            chunks.append(KnowledgeChunk(chunk_id, source, section_heading, part, visibility, approval, topics))
    return chunks


class KnowledgeRetriever:
    """Index Markdown/text files and retrieve only query-relevant chunks."""

    SUPPORTED_SUFFIXES = {".md", ".txt"}

    def __init__(self, directory: Path, index_path: Path, max_chunk_chars: int = 2_000) -> None:
        self.directory = directory
        self.index_path = index_path
        self.max_chunk_chars = max_chunk_chars
        self.chunk_count = 0
        self.source_count = 0
        self._build_if_changed()

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            raise FileNotFoundError(f"Knowledge directory not found: {self.directory}")
        return [p for p in sorted(self.directory.rglob("*")) if p.is_file() and p.suffix.lower() in self.SUPPORTED_SUFFIXES]

    def _fingerprint(self, files: Iterable[Path]) -> str:
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.relative_to(self.directory).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def _connect(self) -> sqlite3.Connection:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, heading TEXT NOT NULL,
            text TEXT NOT NULL, visibility TEXT NOT NULL,
            approval_required INTEGER NOT NULL, topics TEXT NOT NULL)""")
        return connection

    def _build_if_changed(self) -> None:
        files = self._files()
        if not files:
            raise ValueError(f"No Markdown or text knowledge found in {self.directory}")
        fingerprint = self._fingerprint(files)
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key='fingerprint'").fetchone()
            if not row or row[0] != fingerprint:
                chunks: list[KnowledgeChunk] = []
                for path in files:
                    source = path.relative_to(self.directory).as_posix()
                    chunks.extend(_split_markdown(source, path.read_text(encoding="utf-8"), self.max_chunk_chars))
                connection.execute("DELETE FROM chunks")
                connection.executemany(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(c.id, c.source, c.heading, c.text, c.visibility, int(c.approval_required), json.dumps(c.topics)) for c in chunks],
                )
                connection.execute("INSERT OR REPLACE INTO metadata VALUES ('fingerprint', ?)", (fingerprint,))
                connection.commit()
            self.chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            self.source_count = connection.execute("SELECT COUNT(DISTINCT source) FROM chunks").fetchone()[0]

    def _allowed_chunks(self, audience: str) -> list[KnowledgeChunk]:
        allowed = ("public", "recruiter", "owner_only") if audience == "owner" else ("public", "recruiter")
        placeholders = ",".join("?" for _ in allowed)
        with closing(self._connect()) as connection:
            rows = connection.execute(f"SELECT * FROM chunks WHERE visibility IN ({placeholders})", allowed).fetchall()
        return [KnowledgeChunk(r["id"], r["source"], r["heading"], r["text"], r["visibility"], bool(r["approval_required"]), tuple(json.loads(r["topics"]))) for r in rows]

    def search(
        self,
        query: str,
        audience: str = "recruiter",
        limit: int = 4,
        max_characters: int = 4_500,
        min_score: float = 1.25,
        max_files: int = 3,
    ) -> RetrievalResult:
        if audience not in {"recruiter", "owner"}:
            raise ValueError("audience must be recruiter or owner")
        chunks = self._allowed_chunks(audience)
        query_lower = " ".join(query.lower().split())
        if query_lower.strip(".!?, ") in NO_RETRIEVAL_MESSAGES:
            return RetrievalResult("", (), ())
        raw_terms = set(_tokens(query))
        if raw_terms & UNRELATED_TASK_TERMS and not raw_terms & CAREER_CONTEXT_TERMS:
            return RetrievalResult("", (), ())
        broad_query = bool(raw_terms & {"background", "resume", "cv", "overview"})
        query_terms = [term for term in raw_terms if term not in STOPWORDS]
        for phrase, related in CONCEPTS.items():
            phrase_terms = set(_tokens(phrase))
            if phrase in query_lower or phrase_terms.issubset(set(query_terms)):
                query_terms.extend(term for item in related for term in _tokens(item))
        query_set = set(query_terms)
        if not query_set:
            return RetrievalResult("", (), ())
        phrases = _query_phrases(_tokens(query))

        tokenized = [_tokens(c.text) for c in chunks]
        document_frequency = {term: sum(term in set(doc) for doc in tokenized) for term in query_set}
        average_length = sum(map(len, tokenized)) / max(len(tokenized), 1)
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk, document in zip(chunks, tokenized):
            frequencies = {term: document.count(term) for term in query_set}
            score = 0.0
            for term, frequency in frequencies.items():
                if not frequency:
                    continue
                inverse = math.log(1 + (len(chunks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(document) / max(average_length, 1)))
            heading_tokens = set(_tokens(f"{Path(chunk.source).stem} {chunk.heading}"))
            topic_tokens = set(_tokens(" ".join(chunk.topics)))
            score += 2.4 * len(query_set & heading_tokens)
            score += 1.7 * len(query_set & topic_tokens)

            matched = query_set & set(document)
            # Reward chunks that answer the whole question rather than repeating
            # one popular keyword many times.
            score += 3.0 * (len(matched) / len(query_set))
            window = _minimum_window(document, query_set)
            if window is not None:
                score += 4.0 / (1.0 + math.log(window))

            searchable_tokens = _tokens(
                f"{Path(chunk.source).stem} {chunk.heading} {' '.join(chunk.topics)} {chunk.text}"
            )
            searchable = " ".join(searchable_tokens)
            for phrase_tokens in phrases:
                phrase = " ".join(phrase_tokens)
                if phrase in searchable:
                    score += 2.0 + 0.8 * len(phrase_tokens)
            topic_text = " ".join(chunk.topics).lower()
            for phrase in CONCEPTS:
                if phrase in query_lower and phrase in topic_text:
                    score += 7.0
            normalized_heading = " ".join(_tokens(chunk.heading))
            normalized_source = " ".join(_tokens(Path(chunk.source).stem))
            if normalized_heading and normalized_heading in query_lower:
                score += 6.0
            if normalized_source and normalized_source in query_lower:
                score += 4.0
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))

        if not scored or scored[0][0] < min_score:
            return RetrievalResult("", (), ())

        # Stage one chooses files. A specific query normally yields one file;
        # broad queries may use up to max_files when their scores are competitive.
        best_score = scored[0][0]
        relative_cutoff = max(min_score, best_score * (0.22 if broad_query else 0.38))
        if broad_query:
            limit = max(limit, 5)
        file_scores: dict[str, float] = {}
        for score, chunk in scored:
            if score < relative_cutoff:
                continue
            file_scores[chunk.source] = max(file_scores.get(chunk.source, 0.0), score)
        selected_files = {
            source for source, _ in sorted(
                file_scores.items(), key=lambda item: (-item[1], item[0])
            )[:max_files]
        }

        candidates = [
            (score, chunk) for score, chunk in scored
            if score >= relative_cutoff and chunk.source in selected_files
        ]
        selected: list[KnowledgeChunk] = []
        used = 0
        # Maximal marginal relevance: retain relevance while avoiding four
        # near-duplicate sections that crowd out complementary evidence.
        while candidates and len(selected) < limit:
            best_index = 0
            best_utility = float("-inf")
            for index, (score, chunk) in enumerate(candidates):
                chunk_terms = set(_tokens(f"{chunk.heading} {chunk.text}"))
                redundancy = max(
                    (
                        len(chunk_terms & set(_tokens(f"{item.heading} {item.text}")))
                        / max(len(chunk_terms | set(_tokens(f"{item.heading} {item.text}"))), 1)
                    )
                    for item in selected
                ) if selected else 0.0
                source_penalty = 0.35 * sum(item.source == chunk.source for item in selected)
                utility = score - (best_score * 0.32 * redundancy) - source_penalty
                if utility > best_utility:
                    best_index, best_utility = index, utility
            _, chunk = candidates.pop(best_index)
            rendered = self._render(chunk)
            if selected and used + len(rendered) > max_characters:
                continue
            selected.append(chunk)
            used += len(rendered)
        context = "\n\n".join(self._render(chunk) for chunk in selected)
        sources = tuple(dict.fromkeys(f"{chunk.source}#{chunk.heading}" for chunk in selected))
        return RetrievalResult(context, sources, tuple(selected))

    def search_many(
        self,
        queries: list[str],
        audience: str = "recruiter",
        limit_per_query: int = 3,
        max_characters: int = 7_000,
    ) -> RetrievalResult:
        """Retrieve evidence for every part of a multi-question message."""
        selected: list[KnowledgeChunk] = []
        seen: set[str] = set()
        used = 0
        for query in queries:
            result = self.search(
                query,
                audience=audience,
                limit=limit_per_query,
                max_characters=max_characters,
                max_files=2,
            )
            for chunk in result.chunks:
                if chunk.id in seen:
                    continue
                rendered = self._render(chunk)
                if selected and used + len(rendered) > max_characters:
                    continue
                selected.append(chunk)
                seen.add(chunk.id)
                used += len(rendered)
        context = "\n\n".join(self._render(chunk) for chunk in selected)
        sources = tuple(
            dict.fromkeys(f"{chunk.source}#{chunk.heading}" for chunk in selected)
        )
        return RetrievalResult(context, sources, tuple(selected))

    @staticmethod
    def _render(chunk: KnowledgeChunk) -> str:
        approval = "yes" if chunk.approval_required else "no"
        return f"[SOURCE: {chunk.source} | SECTION: {chunk.heading} | APPROVAL REQUIRED: {approval}]\n{chunk.text}\n[END SOURCE]"
