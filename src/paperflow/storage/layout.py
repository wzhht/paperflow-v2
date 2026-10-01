import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from paperflow.utils.doi import normalize_doi

WINDOWS_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def doi_to_dirname(
    value: str,
    max_length: int = 120,
) -> str:
    """
    Convert a DOI into a Windows-safe directory name.

    Example:

        10.1007/s12273-026-1484-2

    becomes:

        10.1007_s12273-026-1484-2

    Very long DOI names are truncated and receive a short
    deterministic hash suffix.
    """

    doi = normalize_doi(value)

    name = WINDOWS_INVALID_CHARS_RE.sub(
        "_",
        doi,
    )

    # Windows does not allow names ending in space or dot.
    name = name.rstrip(" .")

    if len(name) <= max_length:
        return name

    digest = hashlib.sha256(doi.encode("utf-8")).hexdigest()[:12]

    suffix = f"--{digest}"

    keep = max_length - len(suffix)

    return name[:keep] + suffix


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    input: Path
    library: Path
    manifests: Path
    logs: Path
    cache: Path

    def ensure(self) -> None:
        """
        Create the workspace directory structure.
        """

        self.input.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.library.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.manifests.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.logs.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.cache.mkdir(
            parents=True,
            exist_ok=True,
        )


@dataclass(frozen=True)
class PaperPaths:
    doi: str
    paper_id: str
    directory: Path

    metadata_json: Path

    pdf: Path

    xml: Path
    jats_xml: Path
    html: Path

    raw_md: Path
    llm_md: Path

    tables_md: Path
    tables_json: Path

    qa_json: Path

    def ensure(self) -> None:
        """
        Create this paper's directory if necessary.
        """

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def build_workspace_paths(
    root: str | Path = "workspace",
) -> WorkspacePaths:
    """
    Build the standard PaperFlow workspace paths.

    This function does not create directories.
    Call .ensure() when creation is desired.
    """

    root = Path(root)

    return WorkspacePaths(
        root=root,
        input=root / "input",
        library=root / "library",
        manifests=root / "manifests",
        logs=root / "logs",
        cache=root / "cache",
    )


def build_paper_paths(
    doi: str,
    library_root: str | Path = "workspace/library",
) -> PaperPaths:
    """
    Build all standard output paths for one DOI.

    This function does not create directories.
    Call .ensure() when creation is desired.
    """

    normalized_doi = normalize_doi(doi)

    paper_id = doi_to_dirname(normalized_doi)

    directory = Path(library_root) / paper_id

    return PaperPaths(
        doi=normalized_doi,
        paper_id=paper_id,
        directory=directory,
        metadata_json=directory / "metadata.json",
        pdf=directory / "paper.pdf",
        xml=directory / "paper.xml",
        jats_xml=directory / "paper.jats.xml",
        html=directory / "paper.html",
        raw_md=directory / "paper_raw.md",
        llm_md=directory / "paper_llm.md",
        tables_md=directory / "tables.md",
        tables_json=directory / "tables.json",
        qa_json=directory / "qa.json",
    )
