# 12-Step ML Framework — DE Layer (Steps 1–3, 11)
### Production-grade Data Engineering foundation for end-to-end ML pipelines

> **Status:** DE Layer complete (Steps 1–3, 11) · MLE Layer in progress (Steps 4–6) · DS Layer upcoming (Steps 7–10)

---

## What This Is

A reusable, engineering-grade ML framework built from scratch — designed to work across **four problem types**:

| Problem Type | Example Dataset |
|---|---|
| Classification | Telco Customer Churn ← *current* |
| Regression | Bulldozer Price Prediction |
| Time Series | Sales Forecasting |
| A/B Testing | Experiment Analysis |

The framework is not a notebook. It is a **modular pipeline system** where every step has a dedicated orchestrator, every module writes a structured artifact, and every run produces a complete, auditable evidence chain.

---

## What It Found (Before Any Modeling)

Running the DE layer on the Telco Churn dataset (7,043 rows · 21 features), the pipeline automatically detected:

```
TotalCharges ≈ MonthlyCharges × tenure
```

**99.2% of TotalCharges values fall within a [0.8, 1.2] ratio band** of that product. The feature is a derived proxy — not an independent signal. Including all three in a model inflates feature importance and hides the actual drivers of churn.

The pipeline caught it. No manual EDA. No domain guesswork.

Final governance output:
```
releasable: True  |  reasons: []  |  22 artifacts indexed  |  all run_ids consistent
```

---

## The 12-Step Framework

```
DE Layer  ──────────────────────────────────────────────
  Step 1   Setup & Environment
  Step 2   Data Quality          (10 modules)   ✅ complete
  Step 3   Data Integrity        (5 modules)    ✅ complete
  Step 11  Governance            (4 modules)    ✅ complete

MLE Layer ──────────────────────────────────────────────
  Step 4   Split Strategy                       🔄 in progress
  Step 5   Feature Engineering Pipeline
  Step 6   Modeling Pipeline

DS Layer  ──────────────────────────────────────────────
  Step 7   Validation & Metrics
  Step 8   Error Analysis & Slicing
  Step 9   Explainability & Interpretability
  Step 10  Business Translation & Insights
  Step 12  Next Steps / Future Work
```

Steps 1–3 and 11 are **problem-type agnostic** — they run identically for classification, regression, time series, and A/B testing. Only Steps 4–10 swap task-specific components.

---

## DE Layer — Module Map

### Step 1 · Setup & Environment
| What | How |
|---|---|
| Multi-YAML deep merge | `base.yaml` → layer configs → env overrides. Later files win. |
| ctx construction | Single runtime object carrying merged config, paths, logger, run_id. |
| Reproducibility | Seeds Python, NumPy, and hash RNG from YAML. |
| Config snapshot | Persists the full merged config as a JSON artifact — Step 11 uses it for lineage. |

### Step 2 · Data Quality (10 modules)
| Module | What it does |
|---|---|
| 2.1 Ingestion | CSV / DB loading via YAML SSOT. DB secrets via env only — never in config. |
| 2.2 Contract Validation | Schema enforcement: required columns, dtypes, PK uniqueness. Configurable enforcement. |
| 2.3 Health Check | Per-column diagnostics: missing rate, cardinality, numeric stats, signal tags. |
| 2.4 Semantic Checks | Business rule engine (`telco_v1`): tenure range, negative charges, label values. Evidence-only — no rows dropped. |
| 2.5 Readiness | Classification task validation: min rows, label missing rate, class balance bounds. |
| 2.6.1 Domain Core | Task-agnostic: numeric sanity, categorical top-k, positive-rate by segment, leakage pre-scan. |
| 2.6.2 Domain Addon (Telco) | Telco-specific: tenure/charge buckets, TotalCharges proxy scan, anomaly checks, 5 domain hypotheses. |
| 2.7 Distribution | Label balance, Cohen's d effect sizes, categorical positive-rate spread. |
| 2.8 Pre-Analysis Summary | Aggregates 2.2–2.7 into blockers / critical warnings / suggestions. Gate for cleaning. |
| 2.9 Cleaning | Telco-specific hooks on generic engine: TotalCharges imputation via `MonthlyCharges × tenure`, string normalisation, dtype casting, rare-category bucketing. Outputs cleaned `.parquet`. |
| 2.x Orchestrator | SSOT-driven controller: ingestion → diagnostics → cleaning. Prerequisite enforcement. Gate policy. |

### Step 3 · Data Integrity & Anti-Leakage (5 modules)
| Module | What it does |
|---|---|
| 3.1 Row Identity | PK uniqueness + label conflict check per entity. Detects same entity with conflicting labels. |
| 3.2 Temporal Integrity | Timestamp validation, bounds checking, duplicate snapshot detection, out-of-order sequences. |
| 3.3 Label Alignment | Degenerate label check, forbidden feature name scan, label alias detection on sample. |
| 3.4 Leakage Scan | Per-feature catalogue: tags (`near_label`, `deterministic_wrt_label`, `derived_proxy`, `id_like_name`, `high_cardinality`), risk level (high / medium / low). Consumed by Step 4+. |
| 3.5 Integrity Summary | Aggregates 3.1–3.4. Emits `ready_for_step4` flag. |
| 3.x Orchestrator | Loads cleaned parquet from Step 2 artifact (lineage-traced, not passed directly). |

### Step 11 · Governance — Control Plane (4 modules)
| Module | What it does |
|---|---|
| 11.1 Run Manifest | Dataset fingerprint (SHA256 column hash), artifact directory scan, clean dataset reference. Single source of truth for 11.2–11.4. |
| 11.2 Lineage Audit | Verifies required anchor artifacts exist. Cross-checks every artifact's internal `run_id` — detects cross-run contamination. |
| 11.3 Artifact Inventory | Paged, mtime-sorted artifact browser. Lightweight — no hashing (done in 11.1). |
| 11.4 Release Gate | Three-layer policy check: required report statuses → enabled step coverage → hard-severity event hints. Outputs `releasable: true/false` with reasons and remediation. |
| 11.x Orchestrator | 11.1 → 11.2 → 11.3 → 11.4. 11.2 reuses 11.1's in-memory report. Overall status inherits 11.4. |

---

## Core Engineering Decisions

### YAML as Single Source of Truth
Every threshold, schema definition, gate policy, and module toggle lives in config. No magic numbers in code.

```
config/
  base.yaml            ← project, paths, dataset schema, pipeline plan
  data_quality.yaml    ← Step 2 thresholds and rules
  data_integrity.yaml  ← Step 3 thresholds and rules
  governance.yaml      ← Step 11 policies
  overrides/
    dev.yaml           ← local paths, relaxed gates
```

### Orchestrator Pattern — One Controller Per Step
Each step has a dedicated orchestrator. It reads the execution plan from YAML, resolves modules from a registry, and dispatches by contract type:

```
source  →  returns DataFrame (ingestion)
df      →  receives + validates/transforms DataFrame
agg     →  reads upstream artifacts, no DataFrame required
```

Submodules have one job: compute facts and write an artifact. Gate decisions belong to the orchestrator.

### Two-Tier Gate System
```yaml
gate_policy:
  strict: true    # halt on hard-gate failure
  default: soft   # module-level default

steps:
  - id: contract
    gate: hard    # halt on fail
  - id: health
    gate: soft    # warn, continue
```

Same codebase. Strict in production. Permissive in development. No code changes.

### ModuleReport v1 — Universal Output Contract
Every module returns the same JSON schema:

```json
{
  "schema_version": 1,
  "run_id": "20260222-231948-167",
  "module": { "stage": "data_quality", "step": "2.2", "name": "contract" },
  "summary": { "overall_status": "warn", "issues": [], "warnings": ["dtype_issues_detected"] },
  "checks": { "event_hints": { "version": 1, "hints": [...] } },
  "thresholds_used": { ... },
  "refs": { "self": { ... } }
}
```

Step 11 can audit any step's output because the schema is always identical.

### Event Hints — Structured Signals, Not Log Messages
```json
{
  "code": "leakage_scan_derived_proxy_features_detected",
  "severity_signal": "risk",
  "evidence_path": "checks.derived_proxy_scan.flagged",
  "context": { "n_flagged": 1, "flagged_features": ["TotalCharges"] },
  "remediation": {
    "action": "review_derived_proxy_features_for_collinearity",
    "safe": true,
    "post_check": "confirm handling documented in 4.x/5.x"
  }
}
```

Severity signals: `hard` · `fixable` · `risk` · `info`

The release gate scans every upstream report for `hard` hints and blocks the run — regardless of `overall_status`.

### Fail-Safe Execution
If a module crashes, the orchestrator builds an exception report, persists a safety-net artifact, and continues. The pipeline always produces a complete audit trail — even in partial failure.

### Prerequisite Enforcement
```
cleaning  →  requires  pre_analysis_summary
lineage_audit  →  requires  governance_manifest
```
Enforced deterministically. No convention. No documentation dependency.

---

## Project Structure

```
ml-framework-telco/
├── config/
│   ├── base.yaml
│   ├── data_quality.yaml
│   ├── data_integrity.yaml
│   ├── governance.yaml
│   └── overrides/
│       └── dev.yaml
├── src/
│   ├── pipeline/
│   │   ├── data_quality/       # Step 2 module implementations
│   │   ├── data_integrity/     # Step 3 module implementations
│   │   ├── event_hints.py      # Event hint builder
│   │   ├── reporting.py        # ModuleReport v1 builder
│   │   ├── orchestrator_common.py
│   │   └── runtime.py          # ctx / run_id initialisation
│   └── utils/
│       ├── artifact_utils.py   # SSOT artifact path resolution
│       ├── cfg_utils.py        # Type-safe YAML config accessors
│       ├── path_utils.py
│       └── ...
├── notebooks/
│   └── Churn.ipynb             # Steps 1–3, 11 end-to-end
├── data/
│   └── raw/                    # ← not committed
├── artifacts/                  # ← not committed
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quickstart

```bash
git clone https://github.com/kennyoomega/ml-framework-telco
cd ml-framework-telco
pip install -r requirements.txt
```

Add your data to `data/raw/`, set your root path in `config/overrides/dev.yaml`:

```yaml
paths:
  root: "/your/absolute/path/to/ml-framework-telco"
```

Open `notebooks/Churn.ipynb` and run all cells. The orchestrators handle the rest.

---

## Key Dependencies

```
pandas · numpy · scikit-learn · pyyaml · pyarrow
```

Python 3.10+

---

## What's Next

- [ ] Step 4 — Split Strategy (time-aware, stratified, group-based)
- [ ] Step 5 — Feature Engineering Pipeline
- [ ] Step 6 — Modeling Pipeline (interchangeable task heads)
- [ ] Step 7–10 — DS Layer (metrics, slicing, explainability, business translation)
- [ ] Apply full framework to regression, time series, and A/B test datasets

---

## Author

**Siyu Chen**
Data Engineering · ML Engineering · Data Science
Copenhagen, Denmark · Open to relocation (Denmark / Netherlands)

[LinkedIn](https://linkedin.com/in/yourprofile) · [GitHub](https://github.com/kennyoomega)