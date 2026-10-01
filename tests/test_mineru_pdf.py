import subprocess
import zipfile
from pathlib import Path

import pytest

from paperflow.parsers import mineru_pdf
from paperflow.parsers.mineru_pdf import (
    MinerUArtifactError,
    MinerUExecutionError,
    parse_pdf_with_mineru,
)


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    pdf = tmp_path / "paper.pdf"
    executable = tmp_path / "mineru-kit.exe"
    output = tmp_path / "result.zip"

    pdf.write_bytes(b"%PDF-1.4\n")
    executable.write_text(
        "fake executable",
        encoding="utf-8",
    )

    return pdf, executable, output


def test_parse_pdf_with_mineru_accepts_valid_zip(
    tmp_path,
    monkeypatch,
):
    pdf, executable, output = _files(
        tmp_path
    )

    def fake_run(
        command,
        **kwargs,
    ):
        output_index = (
            command.index("-o")
            + 1
        )

        mineru_output_dir = Path(
            command[
                output_index
            ]
        )

        generated_zip = (
            mineru_output_dir
            / f"{pdf.stem}.zip"
        )

        with zipfile.ZipFile(
            generated_zip,
            "w",
        ) as archive:
            archive.writestr(
                "structured_content.json",
                '{"pages": []}',
            )

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(
        mineru_pdf.subprocess,
        "run",
        fake_run,
    )

    result = parse_pdf_with_mineru(
        pdf,
        output,
        executable=executable,
        tier="advanced",
    )

    assert result.input_pdf == pdf
    assert result.output_zip == output

    assert output.is_file()

    assert (
        "structured_content.json"
        in result.artifact_names
    )

    assert zipfile.is_zipfile(
        output
    )


def test_parse_pdf_with_mineru_reports_process_failure(
    tmp_path,
    monkeypatch,
):
    pdf, executable, output = _files(tmp_path)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            7,
            stdout="",
            stderr="MinerU failed",
        )

    monkeypatch.setattr(
        mineru_pdf.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(MinerUExecutionError):
        parse_pdf_with_mineru(
            pdf,
            output,
            executable=executable,
        )


def test_parse_pdf_with_mineru_requires_structured_content(
    tmp_path,
    monkeypatch,
):
    pdf, executable, output = _files(tmp_path)

    def fake_run(command, **kwargs):
        with zipfile.ZipFile(
            output,
            "w",
        ) as archive:
            archive.writestr(
                "markdown.md",
                "# Paper\n",
            )

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(
        mineru_pdf.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(MinerUArtifactError):
        parse_pdf_with_mineru(
            pdf,
            output,
            executable=executable,
        )
