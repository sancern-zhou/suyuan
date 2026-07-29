"""Pure helpers for stable chunk identity and incremental document diffs."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_chunk_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkDraft:
    chunk_key: str
    content_hash: str
    index_hash: str
    chunk_index: int
    content: str
    embedding_text: str
    context_prefix: str = ""
    start_char: int | None = None
    end_char: int | None = None
    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkDiff:
    reused: list[ChunkDraft]
    added: list[ChunkDraft]
    removed: list[ChunkDraft]


def build_chunk_drafts(chunks: Iterable[Mapping[str, Any]]) -> list[ChunkDraft]:
    occurrences: Counter[str] = Counter()
    drafts: list[ChunkDraft] = []

    for chunk_index, chunk in enumerate(chunks):
        content = str(chunk.get("content") or "")
        embedding_text = str(chunk.get("embedding_text") or content)
        context_prefix = str(chunk.get("context_prefix") or "")
        content_hash = _hash_text(normalize_chunk_text(content))
        occurrence = occurrences[content_hash]
        occurrences[content_hash] += 1
        chunk_key = f"{content_hash}:{occurrence}"
        index_hash = _hash_text(
            "\x1f".join(
                (
                    normalize_chunk_text(embedding_text),
                    normalize_chunk_text(context_prefix),
                )
            )
        )
        raw_section_path = chunk.get("section_path") or ()

        drafts.append(
            ChunkDraft(
                chunk_key=chunk_key,
                content_hash=content_hash,
                index_hash=index_hash,
                chunk_index=chunk_index,
                content=content,
                embedding_text=embedding_text,
                context_prefix=context_prefix,
                start_char=chunk.get("start_char"),
                end_char=chunk.get("end_char"),
                page_number=chunk.get("page_number"),
                section_path=tuple(str(part) for part in raw_section_path),
                metadata=dict(chunk.get("metadata") or {}),
            )
        )

    return drafts


def diff_chunks(old: list[ChunkDraft], new: list[ChunkDraft]) -> ChunkDiff:
    new_by_key = {chunk.chunk_key: chunk for chunk in new}

    reused = [
        chunk
        for chunk in old
        if chunk.chunk_key in new_by_key
        and chunk.index_hash == new_by_key[chunk.chunk_key].index_hash
    ]
    reused_keys = {chunk.chunk_key for chunk in reused}
    removed = [chunk for chunk in old if chunk.chunk_key not in reused_keys]
    added = [chunk for chunk in new if chunk.chunk_key not in reused_keys]

    return ChunkDiff(reused=reused, added=added, removed=removed)
