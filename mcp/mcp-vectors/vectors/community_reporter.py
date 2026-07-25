"""
Community reporter for GraphRAG.

Generates LLM-based reports for detected communities using graph-authoritative
facts (entity_names, file_paths, edge_count) combined with LLM-generated prose
(title, summary, findings).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vectors.community_detector import CommunityCandidate
    from vectors.graph_store import GraphSnapshot
    from vectors.lm_studio import LMStudioClient

logger = logging.getLogger(__name__)

_LLM_MAX_RETRIES = 3
_LLM_BASE_DELAY = 1.0  # seconds; doubles each attempt (1s, 2s, 4s)


def _is_transient_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in (
        "disconnected",
        "connection attempts failed",
        "connection reset",
        "broken pipe",
        "connection error",
    ))


def _extract_community_facts(community: "CommunityCandidate", snapshot: "GraphSnapshot") -> dict:
    """Extract graph-authoritative facts for a community."""
    entity_ids_set = set(community.entity_ids)

    id_to_name: dict[str, str] = {e["id"]: e["name"] for e in snapshot.entities}

    entity_names = []
    for entity in snapshot.entities:
        if entity["id"] in entity_ids_set:
            entity_names.append(entity["name"])

    edges_in_community = [
        e for e in snapshot.edges
        if e["source_id"] in entity_ids_set and e["target_id"] in entity_ids_set
    ]
    edge_count = len(edges_in_community)

    top_edges = sorted(
        edges_in_community,
        key=lambda e: (
            id_to_name.get(e["source_id"], e["source_id"]),
            id_to_name.get(e["target_id"], e["target_id"]),
        ),
    )[:15]

    edge_triples = [
        (
            id_to_name.get(e["source_id"], e["source_id"]),
            e.get("edge_type", "related"),
            id_to_name.get(e["target_id"], e["target_id"]),
        )
        for e in top_edges
    ]

    return {
        "entity_names": sorted(entity_names),
        "file_paths": sorted(community.file_ids),
        "edge_count": edge_count,
        "edge_triples": edge_triples,
    }


async def _read_file_excerpt(path: str, max_chars: int = 800) -> str | None:
    """Return a text excerpt from path, or None if binary or unreadable.
    # UTF-16/UTF-32 files will be skipped by the null-byte probe; acceptable for UTF-8 codebases.
    """
    def _probe() -> bytes:
        try:
            with open(path, "rb") as fh:
                return fh.read(512)
        except OSError:
            return b""

    def _read() -> str:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read(max_chars)
        except OSError:
            return ""

    sample = await asyncio.to_thread(_probe)
    if not sample or b"\x00" in sample:
        return None
    text = await asyncio.to_thread(_read)
    return text.strip() or None


async def _collect_file_excerpts(
    file_paths: list[str],
    max_chars: int = 800,
    max_files: int = 3,
) -> dict[str, str]:
    selected = file_paths[:max_files]
    results = await asyncio.gather(*[_read_file_excerpt(p, max_chars) for p in selected])
    return {p: exc for p, exc in zip(selected, results) if exc is not None}


async def _generate_llm_prose(
    community_facts: dict,
    lm_client: "LMStudioClient",
    include_file_excerpts: bool = False,
) -> dict:
    """Call LLM to generate title/summary/findings. On error, return empty values."""
    if len(community_facts["entity_names"]) < 2:
        return {
            "title": "",
            "summary": "",
            "findings": [],
            "generated_by": getattr(lm_client, "_llm_model", "unknown"),
        }

    edge_lines = "\n".join(
        f"  {src} --[{rel}]--> {tgt}"
        for src, rel, tgt in community_facts.get("edge_triples", [])
    ) or "  (none)"

    excerpts_text = ""
    if include_file_excerpts and community_facts.get("file_paths"):
        excerpts = await _collect_file_excerpts(community_facts["file_paths"])
        if excerpts:
            excerpts_text = "\n\n".join(f"# {p}\n{text}" for p, text in excerpts.items())

    excerpt_section = (
        f"\nFile excerpts:\n{excerpts_text}"
        if include_file_excerpts and excerpts_text
        else ""
    )

    prompt = f"""Analyze this software community cluster:

Entities ({len(community_facts['entity_names'])}): {', '.join(community_facts['entity_names'])}
Files: {', '.join(community_facts['file_paths'])}
Top relationships ({community_facts['edge_count']} total, showing up to 15):
{edge_lines}
{excerpt_section}
Respond with JSON matching this schema exactly:
{{
  "title": "<one-line architectural label>",
  "summary": "<2-3 sentences describing purpose and boundaries>",
  "findings": [
    "<actionable finding 1>",
    "<actionable finding 2>",
    "<actionable finding 3>"
  ]
}}

Rules: 3-5 findings; each finding is one sentence; no bullet prefixes inside the array.""".strip()

    try:
        messages = [
            {"role": "system", "content": (
                "You are a software-architecture analyst. Your input describes a detected module cluster: "
                "entity names, dominant call/import relationships, and optionally short file excerpts. "
                "Identify the architectural role of this cluster and surface concrete, actionable findings "
                "a developer could act on. Respond only with valid JSON — no markdown fences."
            )},
            {"role": "user", "content": prompt},
        ]
        response = None
        for _attempt in range(_LLM_MAX_RETRIES):
            try:
                response = await lm_client.generate_response_with_history(
                    messages, max_tokens=650
                )
                break
            except Exception as _e:
                if _is_transient_llm_error(_e) and _attempt < _LLM_MAX_RETRIES - 1:
                    _delay = _LLM_BASE_DELAY * (2 ** _attempt)
                    logger.warning(
                        "LLM report generation failed (attempt %d/%d): %s — retrying in %.0fs",
                        _attempt + 1, _LLM_MAX_RETRIES, _e, _delay,
                    )
                    await asyncio.sleep(_delay)
                else:
                    raise

        logger.debug(f"LLM raw response type={type(response).__name__} len={len(str(response)) if response else 0}: {response!r}")
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop opening fence line (e.g. "```json" or "```")
            lines = lines[1:]
            # Drop trailing closing fence line if it is exactly "```"
            while lines and lines[-1].strip() == "```":
                lines.pop()
            text = "\n".join(lines).strip()
            logger.debug("Stripped markdown fences from LLM response before JSON parse")
        data = json.loads(text)

        findings_raw = data.get("findings", [])
        if isinstance(findings_raw, str):
            # Normalise legacy string responses: split on newlines, strip bullet prefixes
            findings_raw = [
                f.lstrip("- ").strip()
                for f in findings_raw.splitlines()
                if f.strip()
            ]
        findings = [str(f)[:200] for f in findings_raw if f][:5]

        return {
            "title": data.get("title", "").strip()[:200] if isinstance(data.get("title"), str) else "",
            "summary": data.get("summary", "").strip()[:500] if isinstance(data.get("summary"), str) else "",
            "findings": findings,
            "generated_by": lm_client._llm_model if hasattr(lm_client, "_llm_model") else "unknown",
        }
    except Exception as e:
        logger.warning(f"LLM report generation failed: {e}")
        return {
            "title": "",
            "summary": "",
            "findings": [],
            "generated_by": getattr(lm_client, "_llm_model", "unknown"),
        }


async def generate_report(
    community: "CommunityCandidate",
    snapshot: "GraphSnapshot",
    lm_client: "LMStudioClient",
    include_file_excerpts: bool = False,
) -> dict:
    """
    Generate an LLM-based report for a community.

    Returns dict with keys:
      - community_id, level, parent_id, entity_ids, file_ids (from community, immutable)
      - title, summary, findings (LLM-generated; empty on LLM failure)
      - entity_names, file_paths (graph-authoritative; never from LLM)
      - edge_count (graph-authoritative)
      - generated_by (model name)
      - generated_at (ISO 8601 timestamp)
    """
    facts = _extract_community_facts(community, snapshot)
    prose = await _generate_llm_prose(facts, lm_client, include_file_excerpts=include_file_excerpts)

    return {
        "community_id": community.community_id,
        "level": community.level,
        "parent_id": community.parent_id,
        "entity_ids": list(community.entity_ids),
        "file_ids": list(community.file_ids),
        "title": prose["title"],
        "summary": prose["summary"],
        "findings": prose["findings"],
        "entity_names": facts["entity_names"],
        "file_paths": facts["file_paths"],
        "edge_count": facts["edge_count"],
        "generated_by": prose["generated_by"],
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    }


async def generate_all_reports(
    communities: list["CommunityCandidate"],
    snapshot: "GraphSnapshot",
    lm_client: "LMStudioClient",
    concurrency: int = 3,
    include_file_excerpts: bool = False,
) -> list[dict]:
    """Generate reports for all communities with bounded concurrency."""
    sem = asyncio.Semaphore(concurrency)

    async def bounded_generate(comm: "CommunityCandidate") -> dict:
        async with sem:
            return await generate_report(comm, snapshot, lm_client, include_file_excerpts=include_file_excerpts)

    return await asyncio.gather(*[bounded_generate(c) for c in communities])
