from pathlib import Path

from paperflow.storage import (
    build_paper_paths,
    build_workspace_paths,
    doi_to_dirname,
)


def test_doi_to_dirname():
    assert doi_to_dirname("10.1007/s12273-026-1484-2") == "10.1007_s12273-026-1484-2"


def test_doi_url_to_dirname():
    assert (
        doi_to_dirname("https://doi.org/10.1016/j.buildenv.2025.113229")
        == "10.1016_j.buildenv.2025.113229"
    )


def test_long_doi_is_bounded():
    doi = "10.1234/" + "a" * 300

    result = doi_to_dirname(doi)

    assert len(result) <= 120
    assert "--" in result


def test_build_workspace_paths():
    paths = build_workspace_paths("workspace")

    assert paths.root == Path("workspace")
    assert paths.input == Path("workspace/input")
    assert paths.library == Path("workspace/library")
    assert paths.manifests == Path("workspace/manifests")
    assert paths.logs == Path("workspace/logs")
    assert paths.cache == Path("workspace/cache")


def test_workspace_ensure(tmp_path):
    root = tmp_path / "workspace"

    paths = build_workspace_paths(root)

    paths.ensure()

    assert paths.input.is_dir()
    assert paths.library.is_dir()
    assert paths.manifests.is_dir()
    assert paths.logs.is_dir()
    assert paths.cache.is_dir()


def test_build_paper_paths():
    paths = build_paper_paths("10.1007/s12273-026-1484-2")

    expected_dir = Path("workspace") / "library" / "10.1007_s12273-026-1484-2"

    assert paths.doi == "10.1007/s12273-026-1484-2"

    assert paths.paper_id == "10.1007_s12273-026-1484-2"

    assert paths.directory == expected_dir

    assert paths.metadata_json == expected_dir / "metadata.json"

    assert paths.pdf == expected_dir / "paper.pdf"

    assert paths.xml == expected_dir / "paper.xml"

    assert paths.jats_xml == expected_dir / "paper.jats.xml"

    assert paths.html == expected_dir / "paper.html"

    assert paths.raw_md == expected_dir / "paper_raw.md"

    assert paths.llm_md == expected_dir / "paper_llm.md"

    assert paths.tables_md == expected_dir / "tables.md"

    assert paths.tables_json == expected_dir / "tables.json"

    assert paths.qa_json == expected_dir / "qa.json"


def test_paper_ensure(tmp_path):
    library = tmp_path / "workspace" / "library"

    paths = build_paper_paths(
        "10.1016/j.buildenv.2025.113229",
        library_root=library,
    )

    assert not paths.directory.exists()

    paths.ensure()

    assert paths.directory.is_dir()
