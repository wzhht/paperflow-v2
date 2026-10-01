# PaperFlow V2

[中文](README.md) | **English**

PaperFlow V2 is a local processing pipeline for academic papers. It selects a publisher-specific route from a DOI, prioritizes structured full text when available, uses legally obtained PDFs with an external MinerU environment when necessary, and produces Markdown suitable for downstream LLM reading, retrieval, and analysis while applying conservative scientific-content QA.

The goal is not to make Markdown “pretty”, but to preserve scientific content as safely as possible:

- body text should not be accidentally removed;
- tables and table values should not be silently rewritten;
- References should be preserved;
- image binaries should not appear in the final Markdown;
- standalone display equations may be removed, while scientific symbols and inline quantities in body text should be preserved whenever possible;
- when complete full text cannot be obtained, the result should be explicitly marked as partial / restricted rather than guessed or reconstructed.

> PaperFlow V2 is not a general-purpose DOI downloader and does not bypass paywalls or access controls. All PDFs and restricted content must be obtained legally by the user.

---

## 1. Supported scope

### Elsevier / ScienceDirect

Supported DOI pattern:

```text
10.1016/...
```

Typical route:

```text
DOI
→ Elsevier Article Retrieval XML
→ structured full-text completeness check
→ Markdown
→ conservative cleanup
→ QA
```

Typical source:

```text
elsevier_xml
```

Key behavior:

- prefers publisher-provided structured XML instead of PDF OCR;
- preserves body text, References, and structured tables;
- handles table values conservatively;
- removes unnecessary image content from the final Markdown;
- removes standalone display equations;
- attempts to preserve inline scientific quantities such as `SHGC`, `WWR`, `ACH`, `R²`, `CV(RMSE)`, `NMBE`, `kWh/m²`, `W/m²K`, `°C`, and `%`;
- if an Elsevier “table” is actually only a publisher-provided image with no structured cells, PaperFlow does not fabricate table content. It keeps the usable output and emits a warning.

---

### Building Simulation

Supported DOI pattern:

```text
10.1007/s12273...
```

This route is primarily PDF → MinerU.

Approximate priority:

```text
explicit --pdf
→ exactly one local PDF in the DOI output directory
→ publicly available Springer main-article PDF
→ restricted / partial recovery when no complete PDF is available
```

PDF route:

```text
PDF
→ basic PDF validation
→ external MinerU Advanced
→ structured_content.json
→ PaperFlow renderer
→ QA
```

Typical sources:

```text
building_simulation_pdf_mineru
local_pdf_mineru
```

---

### Nature Portfolio

Supported DOI pattern:

```text
10.1038/...
```

Priority:

```text
explicit --pdf
→ Springer Nature Open Access JATS
→ exactly one local PDF in the DOI output directory
→ public Nature main-article PDF
→ restricted metadata / partial recovery
```

When OA JATS is sufficiently complete:

```text
DOI
→ Springer Nature OA JATS
→ JATS completeness check
→ PaperFlow JATS renderer
→ table numeric QA
```

Typical source:

```text
springer_nature_jats
```

If JATS is incomplete or unavailable but the main-article PDF can be obtained:

```text
PDF
→ MinerU Advanced
→ structured_content.json
→ PaperFlow renderer
→ QA
```

Typical sources:

```text
nature_pdf_mineru
local_pdf_mineru
```

If neither public full text nor a public PDF is available, PaperFlow can save recoverable bibliographic / abstract metadata and explicitly mark the result as:

```text
springer_restricted_partial
Status = warning
```

This output is not a complete full-text article.

---

## 2. Unsupported content

PaperFlow V2 is not currently a general-purpose publisher parser.

Unimplemented DOI routes are rejected, including DOI patterns outside:

```text
10.1016/...
10.1007/s12273...
10.1038/...
```

Do not assume that every `10.1007/...` Springer DOI is supported. The currently implemented Springer route is specifically for Building Simulation:

```text
10.1007/s12273...
```

---

## 3. Environment design

PaperFlow itself is kept lightweight.

PDF parsing runs in a separate MinerU environment, so the PaperFlow V2 environment does not need to install:

```text
torch
transformers
mineru
lmdeploy
```

Recommended layout:

```text
D:\paper\
├─ paperflow-v2\
│  └─ .venv\
├─ mineru4\
│  └─ .venv\
└─ outputs\
```

PaperFlow calls the external MinerU CLI through `MINERU_EXECUTABLE`.

---

## 4. Installation

Enter the repository:

```cmd
cd /d D:\paper\paperflow-v2
```

Create and activate a virtual environment. The Python version should satisfy `requires-python` in `pyproject.toml`:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

Upgrade pip:

```cmd
python -m pip install --upgrade pip
```

Install PaperFlow and development dependencies:

```cmd
python -m pip install -e ".[dev]"
```

Verify the CLI:

```cmd
paperflow --help
```

---

## 5. Configuration

Do not commit real API keys to Git.

The project uses a local:

```text
.env
```

The repository should only contain:

```text
.env.example
```

Suggested `.env`:

```env
ELSEVIER_API_KEY=your_elsevier_key
SPRINGER_OA_API_KEY=your_springer_open_access_key
SPRINGER_META_API_KEY=your_springer_meta_key

MINERU_EXECUTABLE=D:\paper\mineru4\.venv\Scripts\mineru-kit.exe
MINERU_TIER=advanced
```

Where:

- `ELSEVIER_API_KEY`: Elsevier structured full-text route;
- `SPRINGER_OA_API_KEY`: Springer Nature Open Access JATS;
- `SPRINGER_META_API_KEY`: metadata recovery when full text is restricted;
- `MINERU_EXECUTABLE`: path to the external MinerU CLI executable;
- `MINERU_TIER`: currently recommended value is `advanced`.

---

## 6. Processing a single paper

Basic command:

```cmd
paperflow process DOI --library-root "output-directory"
```

Elsevier example:

```cmd
paperflow process 10.1016/j.buildenv.2025.113542 --library-root "D:\paper\outputs\paperflow"
```

Nature example:

```cmd
paperflow process 10.1038/s41467-019-11026-x --library-root "D:\paper\outputs\paperflow"
```

Building Simulation example:

```cmd
paperflow process 10.1007/s12273-026-1484-2 --library-root "D:\paper\outputs\paperflow"
```

PaperFlow creates an independent directory for each DOI, for example:

```text
D:\paper\outputs\paperflow\
└─ 10.1038_s41467-019-11026-x\
```

---

## 7. Explicitly using a local PDF

For PDF-based routes such as Nature / Building Simulation, the main-article PDF can be supplied explicitly:

```cmd
paperflow process 10.1038/example --pdf "D:\papers\article.pdf" --library-root "D:\paper\outputs\paperflow"
```

or:

```cmd
paperflow process 10.1007/s12273-example --pdf "D:\papers\article.pdf" --library-root "D:\paper\outputs\paperflow"
```

`--pdf` has the highest priority.

The Elsevier `10.1016/...` route is structured-XML-first and does not use a local PDF as a replacement for its normal XML route.

---

## 8. What if the PDF becomes available later?

This is a supported PaperFlow V2 workflow.

For example, the first run of a Nature paper may result in:

```text
Source = springer_restricted_partial
Status = warning
```

This means complete public full text was not available at the time.

If the main-article PDF is later obtained legally, place **exactly one** `.pdf` file in that DOI output directory:

```text
D:\paper\outputs\paperflow\
└─ 10.1038_s41558-024-02108-w\
   └─ any-filename.pdf
```

Then rerun the original command:

```cmd
paperflow process 10.1038/s41558-024-02108-w --library-root "D:\paper\outputs\paperflow"
```

PaperFlow will discover the local PDF and rerun the PDF → MinerU route.

Local PDF auto-discovery rules:

```text
0 PDFs
→ continue trying online routes

exactly 1 PDF
→ use it automatically

more than 1 PDF
→ treat as ambiguous and stop; do not guess
```

Do not place the main-article PDF and Supplementary PDF together in the DOI directory.

---

## 9. Batch processing

Prepare a text file with one DOI per line, for example:

```text
10.1016/j.buildenv.2025.113542
10.1007/s12273-026-1484-2
10.1038/s41467-019-11026-x
10.1038/s41558-024-02108-w
```

For example, save it as:

```text
D:\paper\dois.txt
```

Run the batch:

```cmd
paperflow process-list "D:\paper\dois.txt" --library-root "D:\paper\outputs\paperflow_batch"
```

During execution, PaperFlow prints per-paper status lines:

```text
[1/N] DOI -> success (...)
[2/N] DOI -> warning (...)
[3/N] DOI -> FAILED
```

After the batch completes, it generates:

```text
batch_results.csv
```

Use this file to inspect the route, source, status, failures, and warnings for each paper.

If a PDF becomes available later, the whole batch does not need to be rerun. Place the PDF in the corresponding DOI directory and rerun only that paper.

---

## 10. Output files

Different routes generate different intermediate artifacts, but the core outputs usually include:

```text
paper_llm.md
qa.json
```

Other possible files include:

```text
paper_raw.md
paper.xml
paper.jats.xml
springer_oa_response.xml
paper.pdf
mineru.zip
structured_content.json
springer_meta.json
access.json
```

### `paper_llm.md`

Final Markdown intended for downstream LLM reading / RAG / literature analysis.

### `qa.json`

This file should be inspected carefully.

It records:

- DOI;
- route;
- source;
- status;
- whether fallback occurred;
- table QA;
- References checks;
- PDF / MinerU checks;
- warnings;
- failures.

### `access.json`

When complete public full text cannot be obtained, this records the restricted / partial state and instructions for later recovery using a legally obtained PDF.

---

## 11. Status meanings

### `success`

The current route passed the main QA checks with no known warning requiring manual attention.

### `warning`

A usable output was generated, but there is an explicit caveat.

Common cases include:

- complete Nature / Springer full text is not publicly available and only metadata / abstract was saved;
- the PDF → MinerU route produced a non-fatal warning;
- an Elsevier table exists only as an image and has no structured table content;
- another QA condition is acceptable but worth manual review.

`warning` does not mean complete full text.

Always interpret it together with:

```text
Source
qa.json
access.json
```

### `failed`

A hard failure occurred, for example:

- unsupported route;
- XML does not meet the minimum completeness requirement;
- structured table content was lost;
- table numeric audit failed;
- References should exist but are missing;
- PDF is not parseable;
- disallowed images / base64 / display equations remain in the final Markdown.

---

## 12. Scientific-content handling principles

PaperFlow V2 uses a conservative strategy.

### Body text

Body text is preserved as completely as possible and is not compressed into a summary.

### Tables

For structured tables:

- preserve the table;
- preserve cell contents;
- perform table numeric audit on critical routes;
- do not proactively “correct” values;
- do not rewrite scientific data just to improve Markdown appearance.

### Images

The final Markdown does not retain image binaries, including:

```text
Markdown image
HTML <img>
base64 image
MinerU image_source
```

Image captions may be retained when useful.

### Equations

Standalone display equations may be removed to reduce complex LaTeX / OCR noise.

Inline scientific quantities should still be preserved whenever possible, for example:

```text
U-value
SHGC
WWR
ACH
R²
R2
CV(RMSE)
NMBE
kWh/m²
W/m²K
°C
%
```

### References

References are an important part of completeness QA and should not be removed merely to clean up Markdown.

---

## 13. Important limitations

### 13.1 PDF numeric audit is not ground-truth validation of the original PDF

For PDF → MinerU routes, PaperFlow's numeric audit checks consistency between:

```text
MinerU structured_content
→ PaperFlow Markdown
```

It does not prove that MinerU OCR / PDF parsing recognized every number from the original PDF correctly.

In other words:

```text
original PDF → MinerU
```

is still subject to MinerU parsing quality.

For high-risk or critical scientific data, the original PDF should still be checked manually.

---

### 13.2 Image-only tables cannot be reconstructed from nothing

If a publisher provides only a table image and no structured cell data, PaperFlow does not OCR it and pretend the result is an exact structured table.

Such cases may be marked as warnings, while the image binary itself is omitted.

---

### 13.3 Restricted results are not complete full text

For example:

```text
Source = springer_restricted_partial
Status = warning
```

This only means PaperFlow saved bibliographic / abstract information that was legally available at the time.

It does not infer, generate, or reconstruct missing body-text sections.

---

### 13.4 The user is responsible for local PDF identity

If a PDF is manually placed in a DOI output directory or supplied with `--pdf`, confirm that it actually corresponds to the target DOI.

PaperFlow is designed primarily to process content and should not be treated as a reliable paper-identity verification tool.

---

### 13.5 API / publisher availability can change

For Elsevier, Springer Nature, and Nature websites, the following may change over time:

- API permissions;
- Open Access status;
- HTTP behavior;
- PDF exposure / availability;
- available metadata fields.

Therefore, the same DOI may follow a different fallback route at a different time, under a different account permission level, or on a different network.

---

### 13.6 No access-control bypass

PaperFlow is not intended to:

- bypass paywalls;
- bypass institutional authentication;
- bypass publisher access controls;
- download content the user is not authorized to access.

For restricted papers, the user should legally obtain the main-article PDF and then process it locally with PaperFlow.

---

## 14. Repository structure

```text
paperflow-v2/
├─ .env.example
├─ .gitignore
├─ README.md
├─ pyproject.toml
│
├─ scripts/
│  ├─ rerender_mineru_batch.py
│  └─ smoke_elsevier_live.py
│
├─ src/
│  └─ paperflow/
│     ├─ batch.py
│     ├─ cli.py
│     ├─ config.py
│     ├─ models.py
│     ├─ pipeline.py
│     ├─ recovery.py
│     ├─ routing.py
│     ├─ cleaners/
│     ├─ parsers/
│     ├─ qa/
│     ├─ sources/
│     ├─ storage/
│     └─ utils/
│
└─ tests/
   └─ test_*.py
```

---

## 15. Development and testing

Format:

```cmd
python -m ruff format src tests scripts
```

Static checks:

```cmd
python -m ruff check src tests scripts
```

Full test suite:

```cmd
pytest -q
```

Local validation of the PaperFlow V2 frozen baseline before commit:

```text
Ruff:   All checks passed
Pytest: 116 passed
```

---

## 16. Current validation snapshot

In one local batch validation run covering 87 DOIs, the final result was:

```text
Total   = 87
Success = 74
Warning = 13
Failed  = 0
```

This is not a cross-publisher general benchmark.

Warnings include restricted partial metadata, PDF/MinerU caveats, image-only tables, and similar cases, so `Success + Warning` must not be interpreted as “complete full text was obtained for every paper”.

The main significance of this result is that, on this validation set, PaperFlow left no unhandled hard failures while still clearly distinguishing complete successes from outputs requiring manual attention.

---

## 17. Recommended workflow

Single paper:

```text
DOI
→ paperflow process
→ inspect Status / Source
→ open paper_llm.md
→ inspect qa.json
```

Batch:

```text
DOI list
→ paperflow process-list
→ inspect batch_results.csv
→ filter warning / failed
→ inspect qa.json / access.json for warnings
→ rerun individual papers when a PDF becomes available later
```

For research use, always retain the original DOI / PDF / publisher source for final verification rather than treating Markdown as the sole source of truth.
