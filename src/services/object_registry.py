"""Object registry service for canonicalizing object names.

Maps raw object names from text to canonical object IDs using synonyms.
"""

from pathlib import Path
from typing import Final

import yaml
from rapidfuzz import fuzz

# Fuzzy matching threshold for near-matches
FUZZY_MATCH_THRESHOLD: Final[float] = 0.9


class ObjectRegistry:
    """Registry for mapping object names to canonical IDs."""

    def __init__(self, registry_path: str | Path) -> None:
        """Initialize object registry from YAML file.

        Args:
            registry_path: Path to registry YAML file

        Raises:
            ValueError: If registry format is invalid
        """
        self.registry_path = Path(registry_path)
        self.objects: dict[str, list[str]] = {}
        self._reverse_index: dict[str, str] = {}
        self._loaded_mtime: float | None = None

        self._load_registry()
        self._build_reverse_index()

    def _load_registry(self) -> None:
        """Load registry from YAML file."""
        if not self.registry_path.exists():
            self.objects = {}
            self._loaded_mtime = None
            return

        self._loaded_mtime = self.registry_path.stat().st_mtime
        with open(self.registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            self.objects = {}
            return

        if "objects" not in data:
            raise ValueError("Registry must have 'objects' key")

        self.objects = data["objects"]

    def _reload_if_changed(self) -> None:
        """Hot-reload the registry when the YAML file changed on disk."""
        try:
            current_mtime = (
                self.registry_path.stat().st_mtime
                if self.registry_path.exists()
                else None
            )
        except OSError:
            return

        if current_mtime == self._loaded_mtime:
            return

        self._load_registry()
        self._build_reverse_index()

    def _build_reverse_index(self) -> None:
        """Build reverse index: synonym -> object_id."""
        self._reverse_index = {}
        for object_id, synonyms in self.objects.items():
            for synonym in synonyms:
                # Normalize: lowercase, strip whitespace
                normalized = synonym.lower().strip()
                self._reverse_index[normalized] = object_id

    def canonicalize_object(self, raw_name: str) -> str | None:
        """Map raw object name to canonical object_id.

        Uses exact match first, then fuzzy matching for near-matches.

        Args:
            raw_name: Raw object name from text

        Returns:
            Canonical object_id if found, None otherwise

        Example:
            >>> from src.config.settings import get_settings
            >>> settings = get_settings()
            >>> registry = ObjectRegistry(settings.object_registry_path)
            >>> registry.canonicalize_object("Stocks & ETFs")
            'wallet.stocks'
            >>> registry.canonicalize_object("CH cluster")
            'data.clickhouse'
            >>> registry.canonicalize_object("Unknown System")
            None
        """
        if not raw_name:
            return None

        self._reload_if_changed()

        normalized = raw_name.lower().strip()

        # Exact match
        if normalized in self._reverse_index:
            return self._reverse_index[normalized]

        # Fuzzy matching (for typos/variations)
        best_match_score = 0.0
        best_match_id = None

        for synonym, object_id in self._reverse_index.items():
            score = fuzz.ratio(normalized, synonym) / 100.0
            if score >= FUZZY_MATCH_THRESHOLD and score > best_match_score:
                best_match_score = score
                best_match_id = object_id

        return best_match_id

    def get_synonyms(self, object_id: str) -> list[str]:
        """Get all synonyms for an object_id.

        Args:
            object_id: Canonical object ID

        Returns:
            List of synonyms

        Example:
            >>> registry.get_synonyms("wallet.stocks")
            ['Stocks & ETFs', 'Stock trading', 'Equity wallet']
        """
        return self.objects.get(object_id, [])

    def get_all_object_ids(self) -> list[str]:
        """Get all registered object IDs.

        Returns:
            List of canonical object IDs
        """
        return list(self.objects.keys())

    def add_synonym(self, object_id: str, synonym: str) -> None:
        """Append a synonym to the registry YAML file (comment-preserving).

        Inserts the synonym line after the last synonym of the object's block
        (or appends a new block for a new object_id) via targeted text edits,
        so YAML comments survive. The result is validated with yaml.safe_load;
        on invalid output the file is rolled back.

        Args:
            object_id: Canonical object ID (existing or new)
            synonym: Synonym to register

        Raises:
            ValueError: If arguments are empty or the edited YAML is invalid
        """
        object_id = object_id.strip()
        synonym = synonym.strip()
        if not object_id or not synonym:
            raise ValueError("object_id and synonym must be non-empty")

        self._reload_if_changed()
        if synonym.lower() in (
            s.lower() for s in self.objects.get(object_id, [])
        ):
            return  # Already registered

        original = (
            self.registry_path.read_text(encoding="utf-8")
            if self.registry_path.exists()
            else "objects:\n"
        )

        quoted = synonym.replace("\\", "\\\\").replace('"', '\\"')
        lines = original.splitlines()

        block_start = None
        for i, line in enumerate(lines):
            if line.strip() == f"{object_id}:" and line.startswith("  "):
                block_start = i
                break

        if block_start is None:
            # New object: append a block at the end of the file
            new_lines = [*lines, f"  {object_id}:", f'    - "{quoted}"']
        else:
            # Existing object: insert after the last synonym of the block
            insert_at = block_start + 1
            for j in range(block_start + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped.startswith("-"):
                    insert_at = j + 1
                elif stripped and not stripped.startswith("#"):
                    break
            new_lines = [
                *lines[:insert_at],
                f'    - "{quoted}"',
                *lines[insert_at:],
            ]

        updated = "\n".join(new_lines) + "\n"

        # Validate before considering the write final; roll back otherwise
        self.registry_path.write_text(updated, encoding="utf-8")
        try:
            data = yaml.safe_load(updated)
            if (
                not isinstance(data, dict)
                or "objects" not in data
                or synonym not in (data["objects"].get(object_id) or [])
            ):
                raise ValueError("edited registry did not contain the new synonym")
        except (yaml.YAMLError, ValueError) as exc:
            self.registry_path.write_text(original, encoding="utf-8")
            raise ValueError(f"Failed to add synonym to registry: {exc}") from exc

        self._load_registry()
        self._build_reverse_index()
