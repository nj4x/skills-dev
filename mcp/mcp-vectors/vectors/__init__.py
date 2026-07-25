"""MCP Vectors - Local semantic search with Qdrant and LM Studio."""

from .config import get_config, Config
from .graph_store import GraphStore, GraphSnapshot, MIGRATION_SENTINEL_FILE
from .lm_studio import LMStudioClient
from .qdrant import (
    QdrantVectorStore,
    QdrantCommunities,
    CommunityCollectionConfigError,
    CollectionMissingError,
)
from .parser import DocumentParser
from .rag import RAGPipeline
from .extraction_cache import ExtractionCache
from .entity_extractor import Entity, Edge, EntityMap, EntityExtractor, annotate_chunks
from .community_detector import detect_communities, DetectorUnavailableError, CommunityCandidate
from .community_reporter import generate_report, generate_all_reports

__all__ = [
    "get_config",
    "Config",
    "GraphStore",
    "GraphSnapshot",
    "MIGRATION_SENTINEL_FILE",
    "LMStudioClient",
    "QdrantVectorStore",
    "QdrantCommunities",
    "CommunityCollectionConfigError",
    "CollectionMissingError",
    "DocumentParser",
    "RAGPipeline",
    "ExtractionCache",
    "Entity",
    "Edge",
    "EntityMap",
    "EntityExtractor",
    "annotate_chunks",
    "detect_communities",
    "DetectorUnavailableError",
    "CommunityCandidate",
    "generate_report",
    "generate_all_reports",
]
