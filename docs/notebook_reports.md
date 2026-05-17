# Federated Case Notebooks

The notebook generator creates Jupyter case-analysis notebooks from
federation-safe artifacts only. It does not query bank SQLite databases and it
does not include raw customer names, raw account identifiers, or raw transaction
rows.

## Generate The Current Canonical Notebook

```powershell
uv run python -m backend.notebooks.generate_case_notebook --stub
```

Outputs land under `out/notebooks/` by default:

- `s1_structuring_ring_artifacts.json`
- `s1_structuring_ring_analysis.ipynb`
- `s1_structuring_ring_artifacts.html`
- `s1_structuring_ring_analysis.html`

Use `--out-dir <path>` to place the notebook elsewhere.

## Generate From The Demo UI

The local control API exposes the same generator to the browser:

```http
POST /sessions/{session_id}/case-notebook
```

The endpoint runs the canonical path to idle if needed, writes the same four
files under `out/ui-notebooks/{session_id}/`, and returns two static HTML
strings: one for the notebook and one for the sanitized artifact bundle. The
Demo Flow page shows sample HTML previews until this endpoint has generated the
current session report.

The frontend also exposes the reports as separate pages:

- `#/notebook` for the notebook HTML.
- `#/artifacts` for the sanitized artifact HTML.

Both pages include a **Show code** toggle. Code cells are collapsed by default
in the generated HTML, so judges can read the analysis first and reveal the
underlying notebook code only when they want it.

## What Goes Into The Notebook

The notebook embeds a typed `CaseNotebookArtifacts` JSON bundle containing:

- F2 graph-pattern request and response.
- Per-bank statistical intermediaries released to F2.
- DP provenance rows for rho, sensitivity, sigma, epsilon display, and argument
  hashes.
- F3 sanctions or PEP response summaries.
- F4 SAR assembly request and SAR draft.
- F5 audit review request and result.
- F6/Lobster Trap policy verdict evidence.
- Wire-level audit events used by F5.

The notebook then reconstructs the pooled statistic by summing same-shaped
per-bank histogram buckets. This shows how the federation produces the
cross-bank AML signal without seeing raw silo rows.

The HTML report includes static graphics generated from the same artifacts:

- Canonical flow diagram from A1 through F5.
- Pooled edge-count and flow-bucket bar charts.
- DP rho-by-bank summary.
- F6/Lobster Trap policy-decision summary.

## Optional LLM Narrative

By default, prose is deterministic template text. To ask the local model route
for bounded notebook prose, use:

```powershell
uv run python -m backend.notebooks.generate_case_notebook --stub --llm-narrative
```

The LLM receives only the typed, sanitized artifact summary and must return a
strict `NotebookNarrative` JSON object. Code cells and artifact data are still
deterministic.

## Future Scenarios

Only `s1_structuring_ring` has a built canonical runner today. S2 and S3 can use
the same notebook path once their orchestrator runs emit a saved
`CaseNotebookArtifacts` bundle:

```powershell
uv run python -m backend.notebooks.generate_case_notebook `
  --artifact-bundle path\to\s2_layering_artifacts.json
```
