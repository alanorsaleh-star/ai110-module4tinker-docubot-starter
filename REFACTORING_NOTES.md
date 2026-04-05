# DocuBot Retrieval Refactoring Summary

## Problem Analysis

**Where was the issue?**
The retrieval logic in `retrieve()` was returning **entire documents** (whole .md files) as the unit of retrieval. This meant:
- A 200-line database schema file would be returned even if only 1 line was relevant
- The LLM had to sift through lots of noise to find the signal
- No guardrail existed for weak evidence—it would answer even with minimal matches

**When did this happen?**
During the scoring/sorting phase in `retrieve()`. The logic would:
1. Score each whole document
2. Sort by score
3. Return top-k documents as-is

## Solution: Paragraph-Level Retrieval + Confidence Guardrail

### Strategy Chosen: **Newline-Separated Sections**

Split each document into paragraphs (blocks separated by `\n`). This gives:
- Simple, consistent parsing rule (no complex NLP needed)
- Natural semantic units (markdown lines, sentences)
- Preserves file source attribution (`[filename]`)
- Easy to maintain and debug

### Changes Made

#### 1. **Index Structure (Fine-Grained)**
Old:
```python
{
    "token": ["AUTH.md", "API_REFERENCE.md"],
    "database": ["DATABASE.md"]
}
```

New:
```python
{
    "token": [("AUTH.md", 0), ("AUTH.md", 2), ("API_REFERENCE.md", 1)],
    "database": [("DATABASE.md", 3)]
}
```

Index now tracks `(filename, paragraph_id)` pairs for precise retrieval.

---

#### 2. **New Helper Method: `get_paragraph()`**
```python
def get_paragraph(self, filename, para_id):
    """Retrieve specific paragraph from a document by index."""
```
Enables extraction of individual paragraphs instead of whole files.

---

#### 3. **Refactored `retrieve()` with Guardrail**

**Key additions:**
- Works on paragraphs, not documents
- **Confidence threshold** parameter (default=1)
- If best score < threshold → return empty list (refusal)

```python
def retrieve(self, query, top_k=3, confidence_threshold=1):
    # ... score each paragraph ...
    
    # GUARDRAIL: Check if best score meets confidence threshold
    best_score = scored_paragraphs[0][0]
    if best_score < confidence_threshold:
        # Weak evidence - refuse to answer
        return []
```

**Why this placement?**
- Decision happens **during retrieval**, not in answer methods
- Explicit and testable
- Prevents LLM from being asked to answer on weak evidence

---

#### 4. **Updated Answer Methods**
Both `answer_retrieval_only()` and `answer_rag()` now:
- Check if `retrieve()` returns empty
- Return explicit refusal rather than generic "I don't know"

Old:
```python
if not snippets:
    return "I do not know based on these docs."
```

New:
```python
if not snippets:
    return "I do not have focused evidence to answer this question. The retrieved sections did not contain enough relevant information."
```

---

## Test Results

✓ Index correctly stores `(filename, para_id)` tuples  
✓ Retrieves focused paragraph snippets instead of whole files  
✓ Guardrail prevents answering on weak evidence (nonsense queries)  
✓ Both retrieval-only and RAG modes respect the guardrail  
✓ Real queries from SAMPLE_QUERIES still retrieve relevant content  

---

## Implications for Evaluation

**Before:** Evaluation checked if correct *files* were retrieved  
**After:** Paragraphs from correct files are retrieved, plus guardrail prevents false answers

The evaluation logic in `evaluation.py` checks file-level hits. This refactoring should:
- Maintain or improve hit rates (more precise retrieval)
- Prevent spurious answers when confidence is low
- Give the LLM cleaner, more focused context per query

---

## Configuration

To adjust confidence threshold in answer methods:

```python
snippets = self.retrieve(query, top_k=3, confidence_threshold=2)  # Stricter
# or
snippets = self.retrieve(query, top_k=3, confidence_threshold=0.5)  # Looser
```

Default is `confidence_threshold=1` (at least 1 query word must match).

