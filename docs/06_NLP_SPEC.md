# 06 — NLP Semantic Change Analysis

**Principle:** runs only on regions that cryptographic localization already flagged; output is advisory
and never alters the verdict. Must degrade gracefully: if models are unavailable, return rule-based results.

## Interface (`app/nlp/classifier.py`)
```python
class ChangeClassifier(Protocol):
    def analyze(self, region: ChangeRegion) -> ChangeAnalysis: ...

@dataclass
class ChangeAnalysis:
    region_id: str
    primary_category: Category
    categories: list[Category]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    similarity: float | None          # cosine similarity, None for pure insert/delete
    entity_changes: list[EntityChange]  # {type, before, after}
    token_diff: list[DiffOp]          # word-level ops for UI highlighting
    explanation: str
    method: Literal["RULES", "RULES+EMBEDDINGS", "RULES+EMBEDDINGS+LLM"]
```

## Categories
| Category | Detected when | Default severity |
|---|---|---|
| `AMOUNT_CHANGE` | money entity multiset differs (₹, Rs., INR, $, USD, "rupees", "lakh", "crore") | HIGH |
| `DATE_CHANGE` | date entity differs (normalized with `dateparser`, DMY preferred) | HIGH |
| `PARTY_CHANGE` | PERSON / ORG entity differs | HIGH |
| `PERCENTAGE_CHANGE` | `\d+(\.\d+)?\s?%` or "per cent" differs | HIGH |
| `NUMBER_CHANGE` | other numeric tokens differ (quantities, IDs, durations) | MEDIUM |
| `OBLIGATION_CHANGE` | modal/negation flip: shall↔may, must↔may, will↔may, added/removed not/no/never/without | CRITICAL |
| `CLAUSE_ADDED` | region type INSERTED | MEDIUM (HIGH if it contains money/date/obligation terms) |
| `CLAUSE_REMOVED` | region type DELETED | MEDIUM (HIGH if it contained money/date/obligation terms) |
| `CLAUSE_MODIFIED` | MODIFIED with no entity/obligation diff and similarity < 0.90 | MEDIUM |
| `MINOR_EDIT` | MODIFIED, similarity ≥ 0.90 and ≤ 3 word tokens changed, no entity/obligation diff | LOW |
Multiple categories may apply; `primary_category` = highest severity, ties by table order.
Overall document severity = max over regions.

## Pipeline per region
1. Word-level diff (`difflib` on `\w+|[^\w\s]` tokens) → `token_diff`, changed-token count.
2. Entity extraction on before/after text: regexes (money, dates, percentages, numbers) **plus**
   spaCy `en_core_web_sm` NER (PERSON, ORG, GPE, MONEY, DATE, PERCENT). Normalize money to a number + currency,
   dates to ISO. Compare as multisets → `entity_changes`.
3. Obligation/negation check on the changed tokens and their sentence.
4. Embeddings (`all-MiniLM-L6-v2`, sentence-transformers, CPU) → cosine similarity (MODIFIED only).
5. Rules above → categories, severity.
6. Explanation: deterministic template, e.g.
   *"In Section 4 (Payment Terms), page 2: the amount changed from ₹50,000 to ₹80,000."*
7. Optional (`NLP_LLM_EXPLANATIONS=true`): send before/after text + detected categories to an LLM for a one-paragraph
   plain-English explanation. Timeout 10 s; on failure fall back to template. Never sends whole documents.

## Engineering rules
- Models load lazily once (module-level singleton), warmed at startup when `NLP_ENABLED=true`.
- Tests use `RuleOnlyClassifier` / a fake embedder so CI needs no model downloads; one slow test marked
  `@pytest.mark.nlp` exercises real models.
- Install extras: `pip install -e ".[nlp]"` then `python -m spacy download en_core_web_sm`.

## Evaluation (see 08)
Labeled pairs from the tamper corpus (the tamper operation *is* the label) → per-category precision/recall/F1,
macro-F1, confusion matrix; ablation: rules only vs rules+embeddings.
