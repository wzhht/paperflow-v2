from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


class MinerUError(RuntimeError):
    """Base MinerU adapter error."""


class MinerUExecutionError(MinerUError):
    """MinerU subprocess failed."""


class MinerUArtifactError(MinerUError):
    """MinerU output artifact was missing or invalid."""


@dataclass(frozen=True)
class MinerUParseResult:
    input_pdf: Path
    output_zip: Path
    artifact_names: tuple[str, ...]


def parse_pdf_with_mineru(
    pdf_path: str | Path,
    output_zip: str | Path,
    *,
    executable: str | Path,
    tier: str = "advanced",
) -> MinerUParseResult:
    """
    Parse one PDF with external MinerU and produce a ZIP artifact.

    PaperFlow intentionally invokes MinerU only through subprocess.
    No MinerU Python package is imported into the PaperFlow environment.

    MinerU receives a temporary output directory rather than a target
    ZIP filename. This avoids CLI ambiguity around single-file versus
    batch output semantics.

    MinerU creates:

        <input_pdf_stem>.zip

    inside that temporary directory. PaperFlow then moves the ZIP to
    the requested canonical output path.
    """

    pdf_path = Path(pdf_path)

    output_zip = Path(output_zip)

    executable = Path(executable)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Input PDF does not exist: {pdf_path}")

    if not executable.is_file():
        raise FileNotFoundError(f"MinerU executable does not exist: {executable}")

    if not tier.strip():
        raise ValueError("MinerU tier cannot be empty.")

    output_zip.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    #
    # Important:
    #
    # mineru-kit supports output directories and generates
    # <input_stem>.zip automatically for --format zip.
    #
    # Using a directory here is more robust than passing a ZIP
    # filename directly and also remains compatible with MinerU's
    # batch-output rules.
    #
    with tempfile.TemporaryDirectory(
        prefix=".mineru-",
        dir=output_zip.parent,
    ) as temporary_directory:
        mineru_output_dir = Path(temporary_directory)

        command = [
            str(executable),
            "parse",
            str(pdf_path),
            "--pages",
            "all",
            "--tier",
            tier,
            "--format",
            "zip",
            "-o",
            str(mineru_output_dir),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if completed.returncode != 0:
            stdout = (completed.stdout or "").strip()

            stderr = (completed.stderr or "").strip()

            details = "\n".join(
                part
                for part in (
                    stdout,
                    stderr,
                )
                if part
            )

            message = f"MinerU failed with exit code {completed.returncode}."

            if details:
                message += "\n" + details

            raise MinerUExecutionError(message)

        expected_zip = mineru_output_dir / f"{pdf_path.stem}.zip"

        if expected_zip.is_file():
            generated_zip = expected_zip

        else:
            #
            # Defensive fallback in case MinerU changes its output
            # naming while still producing exactly one ZIP.
            #
            zip_candidates = sorted(mineru_output_dir.glob("*.zip"))

            if len(zip_candidates) != 1:
                raise MinerUArtifactError(
                    "MinerU completed successfully "
                    "but PaperFlow could not identify "
                    "exactly one ZIP artifact. "
                    f"Expected: {expected_zip}. "
                    f"Found: "
                    f"{[str(path) for path in zip_candidates]}"
                )

            generated_zip = zip_candidates[0]

        if output_zip.exists():
            output_zip.unlink()

        shutil.move(
            str(generated_zip),
            str(output_zip),
        )

    if not output_zip.is_file():
        raise MinerUArtifactError(f"MinerU ZIP artifact was not created: {output_zip}")

    if not zipfile.is_zipfile(output_zip):
        raise MinerUArtifactError(f"MinerU output is not a valid ZIP archive: {output_zip}")

    try:
        with zipfile.ZipFile(
            output_zip,
            "r",
        ) as archive:
            artifact_names = tuple(archive.namelist())

    except (
        OSError,
        zipfile.BadZipFile,
    ) as exc:
        raise MinerUArtifactError(f"Could not read MinerU ZIP artifact: {output_zip}") from exc

    if "structured_content.json" not in artifact_names:
        raise MinerUArtifactError("MinerU ZIP does not contain structured_content.json.")

    return MinerUParseResult(
        input_pdf=pdf_path,
        output_zip=output_zip,
        artifact_names=(artifact_names),
    )
