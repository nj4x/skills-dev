"""Document parser with structure-preserving chunking."""

import logging
import hashlib
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import DEFAULT_EXCLUDED_EXTENSIONS, DEFAULT_EXCLUDED_DIRECTORIES, DEFAULT_EXCLUDED_FILENAMES, sanitize_for_log
from .safety import ExclusionPolicy

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    """A parsed document with metadata and chunks."""
    file_path: str
    file_name: str
    file_hash: str
    file_size: int
    file_type: str
    modified_time: str
    content: str
    chunks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DocumentParser:
    """Parser for various document types with structure-preserving chunking."""
    
    # Known file extensions and their types (for parsing strategy selection)
    # Files not in this list will use "text" type by default
    FILE_TYPES = {
        # Documents
        ".txt": "text",
        ".md": "markdown",
        ".markdown": "markdown",
        ".rst": "text",
        ".pdf": "pdf",
        # Code - Python
        ".py": "python",
        ".pyi": "python",
        ".pyw": "python",
        # Code - JavaScript/TypeScript
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".mts": "typescript",
        ".cts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".vue": "javascript",
        ".svelte": "javascript",
        # Code - JVM
        ".java": "java",
        ".kt": "java",
        ".kts": "java",
        ".scala": "java",
        ".groovy": "java",
        # Code - C/C++
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".hh": "cpp",
        ".hxx": "cpp",
        # Code - Other
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "text",
        ".m": "text",  # Objective-C
        ".mm": "text",  # Objective-C++
        ".cs": "text",  # C#
        ".fs": "text",  # F#
        ".vb": "text",  # Visual Basic
        ".lua": "text",
        ".r": "text",
        ".R": "text",
        ".jl": "text",  # Julia
        ".ex": "text",  # Elixir
        ".exs": "text",
        ".erl": "text",  # Erlang
        ".hrl": "text",
        ".clj": "text",  # Clojure
        ".cljs": "text",
        ".hs": "text",  # Haskell
        ".ml": "text",  # OCaml
        ".mli": "text",
        ".pl": "text",  # Perl
        ".pm": "text",
        ".dart": "text",
        ".nim": "text",
        ".zig": "text",
        ".v": "text",  # V
        ".d": "text",  # D
        # Shell
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".fish": "shell",
        ".ps1": "shell",  # PowerShell
        ".psm1": "shell",
        ".bat": "shell",
        ".cmd": "shell",
        # Data/Config
        ".json": "json",
        ".jsonc": "json",
        ".json5": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "text",
        ".ini": "text",
        ".cfg": "text",
        ".conf": "text",
        ".env": "text",
        ".env.local": "text",
        ".env.development": "text",
        ".env.production": "text",
        ".properties": "text",
        ".xml": "xml",
        ".csv": "csv",
        ".tsv": "text",
        # Query languages
        ".sql": "sql",
        ".graphql": "graphql",
        ".gql": "graphql",
        # Web
        ".html": "html",
        ".htm": "html",
        ".xhtml": "html",
        ".css": "css",
        ".scss": "css",
        ".sass": "css",
        ".less": "css",
        # Documentation
        ".tex": "text",
        ".bib": "text",
        # Build/Project files
        ".gradle": "java",
        ".sbt": "java",
        ".cmake": "text",
        ".make": "text",
        ".makefile": "text",
        "Makefile": "text",
        "Dockerfile": "text",
        "Containerfile": "text",
        ".dockerignore": "text",
        ".gitignore": "text",
        ".gitattributes": "text",
        ".editorconfig": "text",
        ".prettierrc": "json",
        ".eslintrc": "json",
    }
    
    # Patterns for structure detection in different file types
    STRUCTURE_PATTERNS = {
        "markdown": {
            "header": re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE),
            "code_block": re.compile(r"```[\s\S]*?```", re.MULTILINE),
        },
        "python": {
            "class": re.compile(r"^class\s+\w+.*?:", re.MULTILINE),
            "function": re.compile(r"^(?:async\s+)?def\s+\w+.*?:", re.MULTILINE),
        },
        "javascript": {
            "class": re.compile(r"^(?:export\s+)?class\s+\w+", re.MULTILINE),
            "function": re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+\w+", re.MULTILINE),
            "arrow": re.compile(r"^(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\(", re.MULTILINE),
        },
        "typescript": {
            "class": re.compile(r"^(?:export\s+)?class\s+\w+", re.MULTILINE),
            "function": re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+\w+", re.MULTILINE),
            "interface": re.compile(r"^(?:export\s+)?interface\s+\w+", re.MULTILINE),
            "type": re.compile(r"^(?:export\s+)?type\s+\w+", re.MULTILINE),
        },
    }
    
    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        excluded_extensions: Optional[list[str]] = None,
        excluded_directories: Optional[list[str]] = None,
        excluded_filenames: Optional[list[str]] = None,
    ):
        """
        Initialize the document parser.
        
        Args:
            chunk_size: Target size for each chunk in characters
            chunk_overlap: Overlap between consecutive chunks
            excluded_extensions: Extensions to exclude (deny-list approach)
            excluded_directories: Directory names to exclude
            excluded_filenames: Specific filenames to exclude (e.g., .DS_Store)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.excluded_extensions = set(ext.lower() for ext in (excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS))
        self.excluded_directories = set(excluded_directories or DEFAULT_EXCLUDED_DIRECTORIES)
        self.excluded_filenames = set(excluded_filenames or DEFAULT_EXCLUDED_FILENAMES)
        self.exclusion_policy = ExclusionPolicy(
            excluded_extensions=self.excluded_extensions,
            excluded_directories=self.excluded_directories,
            excluded_filenames=self.excluded_filenames,
        )

    def is_supported(self, file_path: Path) -> bool:
        """Check if a file should be indexed (not in exclusion list)."""
        return self.exclusion_policy.should_index_path(file_path).action == "index"

    def is_excluded_directory(self, dir_path: Path) -> bool:
        """Check if a directory should be excluded from traversal."""
        return self.exclusion_policy.is_excluded_directory(dir_path)
    
    def get_file_type(self, file_path: Path) -> str:
        """Get the file type for a path."""
        return self.FILE_TYPES.get(file_path.suffix.lower(), "text")
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of file contents."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def parse_file(self, file_path: Path) -> ParsedDocument:
        """
        Parse a file and extract its content.
        
        Args:
            file_path: Path to the file
            
        Returns:
            ParsedDocument with content and metadata
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not self.is_supported(file_path):
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        file_type = self.get_file_type(file_path)
        stat = file_path.stat()
        
        # Read content based on file type
        if file_type == "pdf":
            content = self._parse_pdf(file_path)
        else:
            content = self._parse_text(file_path)
        
        # Pre-process and optimize content for HTML/JSON files (in-memory only)
        if file_type == "json":
            content = self._optimize_json(content)
        elif file_type == "html":
            content = self._optimize_html(content)
        
        # Create parsed document
        doc = ParsedDocument(
            file_path=str(file_path.absolute()),
            file_name=file_path.name,
            file_hash=self.compute_file_hash(file_path),
            file_size=stat.st_size,
            file_type=file_type,
            modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            content=content,
            metadata={
                "extension": file_path.suffix.lower(),
                "char_count": len(content),
            },
        )
        
        # Generate chunks with structure preservation
        doc.chunks = self._chunk_content(content, file_type)
        doc.metadata["chunk_count"] = len(doc.chunks)
        
        logger.info(
            f"Parsed {sanitize_for_log(file_path.name)}: {len(content)} chars, {len(doc.chunks)} chunks"
        )
        
        return doc
    
    def _parse_text(self, file_path: Path) -> str:
        """Parse a text-based file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with latin-1 encoding
            with open(file_path, "r", encoding="latin-1") as f:
                return f.read()
    
    def _parse_pdf(self, file_path: Path) -> str:
        """Parse a PDF file."""
        try:
            from pypdf import PdfReader
            
            reader = PdfReader(file_path)
            text_parts = []
            
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Failed to parse PDF {sanitize_for_log(str(file_path))}: {e}")
            raise
    
    def _chunk_content(
        self,
        content: str,
        file_type: str,
    ) -> list[dict]:
        """
        Split content into chunks while preserving structure.
        
        Args:
            content: Document content
            file_type: Type of the file (for structure detection)
            
        Returns:
            List of chunk dictionaries
        """
        if not content.strip():
            return []
        
        # Use structure-aware chunking based on file type
        if file_type == "markdown":
            return self._chunk_markdown(content)
        elif file_type == "html":
            return self._chunk_html(content)
        elif file_type == "json":
            return self._chunk_json(content)
        elif file_type in ["python", "javascript", "typescript", "java", "go", "rust"]:
            return self._chunk_code(content, file_type)
        else:
            return self._chunk_text(content)
    
    def _chunk_html(self, content: str) -> list[dict]:
        """
        Chunk HTML content by extracting text from semantic elements.
        
        Uses BeautifulSoup to parse HTML and extract text from meaningful
        elements like paragraphs, table rows, headers, and list items.
        This produces better semantic chunks than treating HTML as plain text.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not available, falling back to text chunking for HTML")
            return self._chunk_text(content)
        
        soup = BeautifulSoup(content, 'lxml')
        
        # Remove script, style, and other non-content elements
        for tag in soup(['script', 'style', 'meta', 'link', 'noscript']):
            tag.decompose()
        
        # Extract text segments from semantic elements
        text_segments = []
        
        # Process headers first (they provide context)
        for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = header.get_text(separator=' ', strip=True)
            if text and len(text) > 10:
                # Prefix with markdown-style header for context
                level = int(header.name[1])
                text_segments.append(('#' * level) + ' ' + text)
        
        # Process table rows - each row often represents a distinct concept
        for table in soup.find_all('table'):
            # Get table headers for context
            headers = []
            header_row = table.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    headers.append(th.get_text(separator=' ', strip=True))
            
            # Process data rows
            for row in table.find_all('tr')[1:] if headers else table.find_all('tr'):
                cells = [td.get_text(separator=' ', strip=True) for td in row.find_all(['td', 'th'])]
                # Combine header + cell for context
                if headers and len(cells) == len(headers):
                    row_text = ' | '.join(f"{h}: {c}" for h, c in zip(headers, cells) if c)
                else:
                    row_text = ' | '.join(c for c in cells if c)
                
                if row_text and len(row_text) > 20:
                    text_segments.append(row_text)
        
        # Process paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(separator=' ', strip=True)
            if text and len(text) > 30:
                text_segments.append(text)
        
        # Process list items
        for li in soup.find_all('li'):
            text = li.get_text(separator=' ', strip=True)
            if text and len(text) > 20:
                text_segments.append('• ' + text)
        
        # Process div/span with significant content (fallback for non-semantic HTML)
        for div in soup.find_all(['div', 'span']):
            # Only process if it has direct text content (not just nested elements)
            direct_text = ''.join(div.find_all(string=True, recursive=False)).strip()
            if direct_text and len(direct_text) > 50:
                text_segments.append(direct_text)
        
        # If no segments extracted, fall back to full text extraction
        if not text_segments:
            full_text = soup.get_text(separator='\n', strip=True)
            if full_text:
                return self._chunk_text(full_text)
            return []
        
        # Remove duplicates while preserving order
        seen = set()
        unique_segments = []
        for seg in text_segments:
            # Normalize for dedup
            normalized = ' '.join(seg.split())
            if normalized not in seen and len(normalized) > 10:
                seen.add(normalized)
                unique_segments.append(seg)
        
        # Now chunk the extracted text segments
        combined_text = '\n\n'.join(unique_segments)
        return self._chunk_text(combined_text)
    
    def _chunk_json(self, content: str) -> list[dict]:
        """
        Chunk JSON content using text-based chunking.
        
        Note: JSON files are pre-formatted in parse_file() via _optimize_json()
        before reaching this method, so the content is already properly formatted
        with newlines for effective chunking.
        """
        # Content is already optimized/formatted by _optimize_json() in parse_file()
        # Just use text chunking which will split on newlines/paragraphs
        return self._chunk_text(content)
    
    def _chunk_markdown(self, content: str) -> list[dict]:
        """Chunk markdown content preserving headers and sections."""
        chunks = []
        current_chunk = []
        current_size = 0
        current_pos = 0
        chunk_start = 0
        
        # Split by lines, keeping track of headers
        lines = content.split("\n")
        
        for line in lines:
            line_with_newline = line + "\n"
            line_size = len(line_with_newline)
            
            # Check if this is a header
            is_header = line.startswith("#")
            
            # Check if we should start a new chunk
            should_split = (
                current_size + line_size > self.chunk_size
                and current_chunk
            )
            
            # If header and we have content, consider starting new chunk
            if is_header and current_chunk and current_size > self.chunk_size // 2:
                should_split = True
            
            if should_split:
                # Save current chunk
                chunk_text = "".join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        # chunk_id == positional index at append time; this is the same
                        # value used by make_chunk_point_id and entity_extractor (B4/B7 invariant).
                        "chunk_id": len(chunks),
                        "text": chunk_text.strip(),
                        "start_char": chunk_start,
                        "end_char": current_pos,
                    })
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = [overlap_text] if overlap_text else []
                current_size = len(overlap_text) if overlap_text else 0
                chunk_start = current_pos - len(overlap_text) if overlap_text else current_pos
            
            current_chunk.append(line_with_newline)
            current_size += line_size
            current_pos += line_size
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = "".join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    "chunk_id": len(chunks),
                    "text": chunk_text.strip(),
                    "start_char": chunk_start,
                    "end_char": current_pos,
                })
        
        return chunks
    
    def _chunk_code(self, content: str, file_type: str) -> list[dict]:
        """Chunk code content preserving function/class boundaries."""
        chunks = []
        
        # Find structural boundaries
        patterns = self.STRUCTURE_PATTERNS.get(file_type, {})
        boundaries = []
        
        for pattern_type, pattern in patterns.items():
            for match in pattern.finditer(content):
                boundaries.append((match.start(), pattern_type))
        
        # Sort boundaries by position
        boundaries.sort(key=lambda x: x[0])
        
        if not boundaries:
            # No structure found, use simple text chunking
            return self._chunk_text(content)
        
        # Add end boundary
        boundaries.append((len(content), "end"))
        
        current_chunk = []
        current_size = 0
        chunk_start = 0
        last_pos = 0
        
        for boundary_pos, boundary_type in boundaries:
            # Get text up to this boundary
            segment = content[last_pos:boundary_pos]
            
            if current_size + len(segment) > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = "".join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        "chunk_id": len(chunks),
                        "text": chunk_text.strip(),
                        "start_char": chunk_start,
                        "end_char": last_pos,
                    })
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = [overlap_text] if overlap_text else []
                current_size = len(overlap_text) if overlap_text else 0
                chunk_start = last_pos - len(overlap_text) if overlap_text else last_pos
            
            current_chunk.append(segment)
            current_size += len(segment)
            last_pos = boundary_pos
        
        # Handle remaining content
        if current_chunk:
            chunk_text = "".join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    "chunk_id": len(chunks),
                    "text": chunk_text.strip(),
                    "start_char": chunk_start,
                    "end_char": len(content),
                })
        
        return chunks
    
    def _chunk_text(self, content: str) -> list[dict]:
        """Simple text chunking with paragraph awareness and fallback for long lines."""
        chunks = []
        
        # Split by paragraphs (double newlines)
        paragraphs = re.split(r"\n\s*\n", content)
        
        current_chunk = []
        current_size = 0
        current_pos = 0
        chunk_start = 0
        
        for para in paragraphs:
            para_text = para.strip()
            if not para_text:
                continue
            
            # Handle oversized paragraphs (e.g., minified files, single long lines)
            if len(para_text) > self.chunk_size:
                # First, flush any existing chunk
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    if chunk_text.strip():
                        chunks.append({
                            "chunk_id": len(chunks),
                            "text": chunk_text,
                            "start_char": chunk_start,
                            "end_char": current_pos,
                        })
                    current_chunk = []
                    current_size = 0
                
                # Split oversized paragraph into smaller pieces
                sub_chunks = self._split_oversized_text(para_text, current_pos)
                for sub in sub_chunks:
                    chunks.append({
                        "chunk_id": len(chunks),
                        "text": sub["text"],
                        "start_char": sub["start_char"],
                        "end_char": sub["end_char"],
                    })
                
                current_pos += len(para_text) + 2
                chunk_start = current_pos
                continue
            
            para_size = len(para_text) + 2  # +2 for paragraph separator
            
            # Check if paragraph fits in current chunk
            if current_size + para_size > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        "chunk_id": len(chunks),
                        "text": chunk_text,
                        "start_char": chunk_start,
                        "end_char": current_pos,
                    })
                
                # Start new chunk
                # Take last paragraph as overlap if it fits
                if current_chunk and len(current_chunk[-1]) <= self.chunk_overlap:
                    overlap = current_chunk[-1]
                    current_chunk = [overlap]
                    current_size = len(overlap) + 2
                    chunk_start = current_pos - len(overlap) - 2
                else:
                    current_chunk = []
                    current_size = 0
                    chunk_start = current_pos
            
            current_chunk.append(para_text)
            current_size += para_size
            current_pos += para_size
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    "chunk_id": len(chunks),
                    "text": chunk_text,
                    "start_char": chunk_start,
                    "end_char": current_pos,
                })
        
        return chunks
    
    def _split_oversized_text(self, text: str, base_pos: int) -> list[dict]:
        """
        Split oversized text (no paragraph breaks) into chunks.
        
        Attempts to split at sentence boundaries first, then word boundaries,
        falling back to character-based splitting if necessary.
        
        Args:
            text: The oversized text to split
            base_pos: Starting character position for tracking
            
        Returns:
            List of chunk dicts with text, start_char, end_char
        """
        chunks = []
        pos = 0
        
        while pos < len(text):
            # Calculate end position for this chunk
            end = min(pos + self.chunk_size, len(text))
            
            if end < len(text):
                # Try to find a good break point
                segment = text[pos:end]
                
                # Priority 1: Sentence boundary (. ! ?)
                sentence_breaks = [
                    segment.rfind(". "),
                    segment.rfind(".\n"),
                    segment.rfind("! "),
                    segment.rfind("? "),
                ]
                best_break = max((b for b in sentence_breaks if b > self.chunk_size // 3), default=-1)
                
                if best_break == -1:
                    # Priority 2: Clause/phrase boundary (, ; :)
                    clause_breaks = [
                        segment.rfind(", "),
                        segment.rfind("; "),
                        segment.rfind(": "),
                    ]
                    best_break = max((b for b in clause_breaks if b > self.chunk_size // 3), default=-1)
                
                if best_break == -1:
                    # Priority 3: Word boundary (space)
                    best_break = segment.rfind(" ")
                    if best_break < self.chunk_size // 3:
                        best_break = -1  # Too early, ignore
                
                if best_break > 0:
                    end = pos + best_break + 1  # +1 to include the break char
            
            chunk_text = text[pos:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start_char": base_pos + pos,
                    "end_char": base_pos + end,
                })
            
            # Move position with overlap
            if end < len(text):
                # Calculate overlap start
                overlap_start = max(0, end - self.chunk_overlap)
                # Try to start overlap at a word boundary
                space_pos = text[overlap_start:end].find(" ")
                if space_pos > 0:
                    overlap_start += space_pos + 1
                pos = overlap_start
            else:
                pos = end
        
        return chunks
    
    def _get_overlap_text(self, chunks: list[str]) -> str:
        """Get overlap text from the end of current chunks."""
        if not chunks:
            return ""
        
        # Take characters from the end up to overlap size
        full_text = "".join(chunks)
        if len(full_text) <= self.chunk_overlap:
            return full_text
        
        # Try to break at a natural boundary (sentence end, newline)
        overlap_section = full_text[-self.chunk_overlap * 2:]
        
        # Look for sentence end or newline
        boundaries = [
            overlap_section.rfind(". "),
            overlap_section.rfind(".\n"),
            overlap_section.rfind("\n\n"),
            overlap_section.rfind("\n"),
        ]
        
        best_boundary = -1
        for boundary in boundaries:
            if boundary > 0 and boundary > best_boundary:
                best_boundary = boundary
        
        if best_boundary > 0:
            return overlap_section[best_boundary + 1:].lstrip()
        
        return full_text[-self.chunk_overlap:]
    
    def _needs_formatting(self, content: str, threshold: int = 120) -> bool:
        """
        Check if content needs formatting by scanning for long lines.
        
        Args:
            content: File content to check
            threshold: Maximum acceptable line length (default 120 chars)
            
        Returns:
            True if any line exceeds threshold (needs formatting)
        """
        for line in content.split('\n'):
            if len(line) > threshold:
                return True
        return False
    
    def _split_long_line(self, line: str, triggers: str, max_length: int = 1) -> str:
        """
        Split a long line by inserting newlines at trigger characters.
        
        Only inserts newlines when the accumulated line length exceeds max_length,
        and always at the PREVIOUS trigger character position.
        
        Args:
            line: The line to potentially split
            triggers: String of trigger characters (e.g., ',{[' for JSON, '>' for HTML)
            max_length: Maximum line length before splitting (default 120)
            
        Returns:
            Line with newlines inserted at appropriate positions
        """
        if len(line) <= max_length:
            return line
        
        result = []
        current_segment = []
        last_trigger_idx = -1  # Index in current_segment where last trigger was found
        
        for char in line:
            current_segment.append(char)
            
            if char in triggers:
                # Check if we need to break at the PREVIOUS trigger position
                if len(current_segment) > max_length and last_trigger_idx >= 0:
                    # Split at the previous trigger position
                    segment_before = ''.join(current_segment[:last_trigger_idx + 1])
                    segment_after = current_segment[last_trigger_idx + 1:]
                    
                    result.append(segment_before)
                    current_segment = segment_after
                    last_trigger_idx = -1  # Reset after split
                
                # Update last trigger position to current position in segment
                last_trigger_idx = len(current_segment) - 1
        
        # Handle remaining content
        if current_segment:
            remaining = ''.join(current_segment)
            # If remaining is still too long and we have a trigger, split it
            if len(remaining) > max_length and last_trigger_idx >= 0:
                result.append(''.join(current_segment[:last_trigger_idx + 1]))
                result.append(''.join(current_segment[last_trigger_idx + 1:]))
            else:
                result.append(remaining)
        
        return '\n'.join(result)
    
    def _optimize_json(self, content: str) -> str:
        """
        Optimize JSON content for better chunking.
        
        For lines exceeding 120 characters, inserts newlines at natural JSON
        break points (after , { [) only when needed to keep lines under limit.
        Lines already under 120 chars are left unchanged.
        
        Args:
            content: Raw JSON content
            
        Returns:
            Content with long lines split at appropriate positions
        """
        if not self._needs_formatting(content):
            return content  # Already formatted
        
        # Process line by line, only splitting long lines
        lines = content.split('\n')
        result_lines = []
        
        for line in lines:
            if len(line) > 120:
                # Split long line at JSON trigger characters
                split_line = self._split_long_line(line, ',{[')
                result_lines.append(split_line)
            else:
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    def _optimize_html(self, content: str) -> str:
        """
        Optimize HTML content for better chunking.
        
        For lines exceeding 120 characters, inserts newlines after `>` characters
        only when needed to keep lines under limit. Lines already under 120 chars
        are left unchanged.
        
        Args:
            content: Raw HTML content
            
        Returns:
            Content with long lines split at appropriate positions
        """
        if not self._needs_formatting(content):
            return content  # Already formatted
        
        # Process line by line, only splitting long lines
        lines = content.split('\n')
        result_lines = []
        
        for line in lines:
            if len(line) > 120:
                # Split long line at HTML trigger character (>)
                split_line = self._split_long_line(line, '>')
                result_lines.append(split_line)
            else:
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    


def is_supported_file(
    file_path: Path,
    excluded_extensions: Optional[list[str]] = None,
    excluded_directories: Optional[list[str]] = None,
    excluded_filenames: Optional[list[str]] = None,
) -> bool:
    """
    Check if a file should be indexed (not in exclusion lists).
    
    Args:
        file_path: Path to the file
        excluded_extensions: Extensions to exclude (uses defaults if None)
        excluded_directories: Directory names to exclude (uses defaults if None)
        excluded_filenames: Specific filenames to exclude (uses defaults if None)
    
    Returns:
        True if the file should be indexed, False if excluded
    """
    policy = ExclusionPolicy(
        excluded_extensions=excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS,
        excluded_directories=excluded_directories or DEFAULT_EXCLUDED_DIRECTORIES,
        excluded_filenames=excluded_filenames or DEFAULT_EXCLUDED_FILENAMES,
    )
    return policy.should_index_path(file_path).action == "index"
