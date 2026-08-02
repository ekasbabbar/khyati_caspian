"""Versioned knowledge sources for local development and private object storage."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.parse import urljoin
from urllib.request import Request, urlopen


REQUIRED_METADATA = {
    "visibility",
    "approval_required",
    "document_type",
    "topics",
    "description",
    "last_updated",
}
ALLOWED_VISIBILITY = {"public", "recruiter", "owner_only"}


def validate_document(path: str, content: str) -> None:
    """Reject malformed production documents before they enter retrieval."""
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise ValueError(f"Knowledge document {path} has no metadata frontmatter")
    frontmatter = content[4 : content.find("\n---\n", 4)]
    metadata = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip().strip("\"'")
    missing = REQUIRED_METADATA - metadata.keys()
    if missing:
        raise ValueError(f"Knowledge document {path} is missing: {', '.join(sorted(missing))}")
    if metadata["visibility"].lower() not in ALLOWED_VISIBILITY:
        raise ValueError(f"Knowledge document {path} has invalid visibility")
    if not metadata["topics"].strip() or not metadata["description"].strip():
        raise ValueError(f"Knowledge document {path} needs topics and description")


class LocalKnowledgeSource:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def materialize(self) -> Path:
        if not self.directory.is_dir():
            raise FileNotFoundError(f"Knowledge directory not found: {self.directory}")
        documents = [
            path for path in self.directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        ]
        if not documents:
            raise ValueError(f"No knowledge documents found in {self.directory}")
        for path in documents:
            validate_document(
                path.relative_to(self.directory).as_posix(),
                path.read_text(encoding="utf-8"),
            )
        return self.directory


@dataclass(frozen=True)
class ManifestDocument:
    path: str
    url: str
    sha256: str


class ManifestKnowledgeSource:
    """Download an authenticated immutable manifest into a versioned cache."""

    def __init__(self, manifest_url: str, cache_dir: Path, token: str | None = None) -> None:
        self.manifest_url = manifest_url
        self.cache_dir = cache_dir
        self.token = token

    def _read_url(self, url: str) -> bytes:
        headers = {"Accept": "application/json, text/markdown, text/plain"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            return response.read()

    def materialize(self) -> Path:
        manifest = json.loads(self._read_url(self.manifest_url))
        version = str(manifest.get("version", "")).strip()
        if not version or not isinstance(manifest.get("documents"), list):
            raise ValueError("Knowledge manifest requires version and documents")
        safe_version = hashlib.sha256(version.encode()).hexdigest()[:16]
        target = self.cache_dir / safe_version
        ready = target / ".ready"
        if ready.is_file():
            return target

        documents: list[ManifestDocument] = []
        for item in manifest["documents"]:
            document = ManifestDocument(
                path=str(item["path"]),
                url=urljoin(self.manifest_url, str(item["url"])),
                sha256=str(item["sha256"]).lower(),
            )
            relative = PurePosixPath(document.path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe knowledge path: {document.path}")
            documents.append(document)
        if not documents:
            raise ValueError("Knowledge manifest contains no documents")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="knowledge-", dir=self.cache_dir))
        try:
            for document in documents:
                payload = self._read_url(document.url)
                actual = hashlib.sha256(payload).hexdigest()
                if actual != document.sha256:
                    raise ValueError(f"Checksum mismatch for {document.path}")
                content = payload.decode("utf-8")
                validate_document(document.path, content)
                destination = staging.joinpath(*PurePosixPath(document.path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
            (staging / ".ready").write_text(version, encoding="utf-8")
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return target


class S3KnowledgeSource:
    """Materialize a private S3 knowledge release using the EC2 IAM role."""

    def __init__(self, bucket: str, manifest_key: str, cache_dir: Path,
                 region: str | None = None, client=None) -> None:
        if not bucket or not manifest_key:
            raise ValueError("S3 bucket and manifest key are required")
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=region)
        self.bucket, self.manifest_key = bucket, manifest_key
        self.cache_dir, self.client = cache_dir, client

    def _object(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def materialize(self) -> Path:
        manifest = json.loads(self._object(self.manifest_key))
        version = str(manifest.get("version", "")).strip()
        if not version or not isinstance(manifest.get("documents"), list):
            raise ValueError("S3 knowledge manifest requires version and documents")
        target = self.cache_dir / hashlib.sha256(version.encode()).hexdigest()[:16]
        if (target / ".ready").is_file():
            return target
        documents = manifest["documents"]
        if not documents:
            raise ValueError("S3 knowledge manifest contains no documents")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="knowledge-", dir=self.cache_dir))
        try:
            for item in documents:
                path, key = str(item["path"]), str(item["key"])
                expected = str(item["sha256"]).lower()
                relative = PurePosixPath(path)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe knowledge path: {path}")
                if not key or key.startswith("/") or ".." in PurePosixPath(key).parts:
                    raise ValueError(f"Unsafe S3 knowledge key: {key}")
                payload = self._object(key)
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise ValueError(f"Checksum mismatch for {path}")
                content = payload.decode("utf-8")
                validate_document(path, content)
                destination = staging.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
            (staging / ".ready").write_text(version, encoding="utf-8")
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return target
