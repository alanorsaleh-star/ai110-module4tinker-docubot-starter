# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
DocuBot is a retrieval-augmented generation system that answers user questions about project documentation. It supports three modes: naive LLM generation (baseline), retrieval-only (fact-checking), and RAG (balanced clarity + evidence). The goal is to provide accurate, grounded answers with explicit refusals when evidence is weak.

**What inputs does DocuBot take?**  
DocuBot takes:
- A user question (query string)
- Documentation files from the `docs/` folder (markdown and text files)
- An optional LLM client (Gemini) for generation modes
- Environment variables (GEMINI_API_KEY) for LLM access

**What outputs does DocuBot produce?**  
Depending on the mode:
- **Mode 1 (Naive):** A generated answer using full corpus, no evidence attribution
- **Mode 2 (Retrieval only):** Raw document snippets with source file labels
- **Mode 3 (RAG):** An LLM-synthesized answer grounded in specific snippets, with explicit refusals when evidence is insufficient

---

## 2. Retrieval Design

**How does your retrieval system work?**  

- **Indexing:** Documents are split into paragraphs (newline-separated blocks) rather than treated as whole units. An inverted index maps each lowercase word to `(filename, paragraph_id)` tuples, enabling fine-grained retrieval.
  
- **Scoring:** For each query, we extract lowercase words and count how many appear in each candidate paragraph. Score = number of matching query words. This is a simple word-overlap baseline.
  
- **Top-k Selection:** Paragraphs are ranked by score (descending). We return the top `k` snippets (default k=3) as `(filename, text)` tuples.

- **Guardrail:** A **confidence threshold** (default=1) blocks low-quality matches. If the best-scoring paragraph scores below the threshold, the retrieval returns empty, forcing the system to refuse the answer rather than hallucinate.

**What tradeoffs did you make?**  

1. **Granularity:** Paragraphs (on newlines) vs. sentences vs. fixed-size chunks
   - Chose paragraphs for simplicity and markdown-natural semantics
   - Tradeoff: Some paragraphs are short (just a header), while others are long (multiple ideas)

2. **Scoring:** Simple word-overlap vs. TF-IDF vs. semantic similarity
   - Chose word-overlap for interpretability and no external dependencies
   - Tradeoff: Misses semantic matches (synonyms, paraphrasing) but is transparent and debuggable

3. **Guardrail:** Confidence threshold = 1 (at least one word match)
   - Could increase to 2+ for stricter refusal, or lower for lenient acceptance
   - Current setting: Balance between coverage and refusal accuracy

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  

- **Naive LLM mode:** Always calls the LLM. Passes entire corpus of docs as context + user query. LLM generates freely without retrieval constraints.
  
- **Retrieval only mode:** Never calls the LLM. Retrieval alone produces output—raw document snippets labeled with filenames.
  
- **RAG mode:** Calls the LLM only if retrieval returns non-empty results. If retrieval's guardrail triggers (weak evidence), answer is refused before LLM is even invoked, saving API calls.

**What instructions do you give the LLM to keep it grounded?**  

The prompt in `llm_client.py` explicitly instructs Gemini:
1. "Answer using **only** the provided SNIPPETS. Do not use external knowledge."
2. "If the snippets do not contain evidence for your answer, reply: 'I do not know based on the docs I have.'"
3. "Mention which files you relied on in your answer."

These rules attempt to prevent hallucination by restricting the LLM to what is explicitly in the retrieved paragraphs.

---

## 4. Experiments and Comparisons

Tested with 3 identical queries across all three modes (Mode 4 hit API quota).

| Query | Naive LLM | Retrieval Only | RAG | Notes |
|-------|-----------|----------------|-----|-------|
| **Where is the auth token generated?** | Generates 4 detailed scenarios (external IdPs, backend, API keys, refresh flow) with NO evidence from docs—purely generic knowledge | Returns 3 snippets from AUTH.md: mentions `generate_access_token` function, `AUTH_SECRET_KEY` env var, token signing | **Refuses:** "I do not know based on the docs I have" | See analysis below |
| **Is there payment processing in the docs?** | Suggests where to look in general docs (Stripe, PayPal, billing sections, etc.); makes assumptions | Returns 3 irrelevant snippets: SETUP, DATABASE, admin access—none about payments | **Refuses:** "I do not know based on docs I have" | See analysis below |
| **What does /api/projects/<project_id> return?** | Generates a complete JSON response with id, name, description, status, owner_id, budget, timestamps, error codes—ALL HALLUCINATED | Returns 3 snippets: AUTH.md (token generation), API_REFERENCE.md headers, and "404 if project doesn't exist" | **Refuses:** "I do not know based on docs I have" | See analysis below |

**Critical Observations:**

### **Case 1: Where is the auth token generated?**
- **Naive LLM:** ❌ Harmful—confident but ungrounded. Generates a textbook answer covering OAuth, JWT, API keys globally, but the docs are about a simple internal auth system.
- **Retrieval Only:** ✓ Accurate—shows actual snippets mentioning `generate_access_token` function and env vars, but requires user to synthesize meaning.
- **RAG:** ⚠️ Overly cautious—Refuses even though docs contain relevant info. Guardrail (threshold=1) may be too strict; a single word match on "token" or "generate" isn't enough confidence.

### **Case 2: Is there payment processing in the docs?**
- **Naive LLM:** ❌ Harmful—Speaks confidently about how to structure payment docs, but the user docs have NO payment functionality. Makes unfounded assumptions.
- **Retrieval Only:** ❌ Problematic—Returns irrelevant snippets. No clarity for the user that the answer is "no payment mentioned."
- **RAG:** ✓ Correct refusal—Safely says "I don't know" rather than guessing. This is the right behavior.

### **Case 3: What does /api/projects/<project_id> return?**
- **Naive LLM:** ❌ **Hallucination risk highest here.** Generates detailed JSON with fields (status, budget, owner_id, timestamps) that may not exist in docs. Very confident, very wrong.
- **Retrieval Only:** ❌ Noise—Snippets about auth and API headers don't explain the /projects endpoint. One line mentions "404 if doesn't exist" but lacks full context.
- **RAG:** ✓ Refuses rather than guessing. Given weak evidence, this is the safest choice, even if it frustrates the user.

### **Pattern Summary:**

| Scenario | Winner | Why |
|----------|--------|-----|
| **Weak evidence in docs** | RAG ✓ | Refuses rather than hallucinate |
| **Generic conceptual question** | Naive LLM (but overconfident) | Summarizes general knowledge; RAG refuses |
| **Question outside docs scope** | RAG ✓ | Correctly refuses |
| **Well-covered topic** | RAG (if guardrail tuned) | Retrieval quality good; LLM synthesis adds clarity |
| **User needs raw facts** | Retrieval Only ✓ | Transparent, no interpretation |

**What patterns did you notice?**

1. **Naive LLM is dangerous:** It sounds confident and well-structured, but lacks grounding. It draws on general knowledge of APIs, authentication, and databases that may not match the specific docs. Example: Auth token generation answer covers scenarios (OAuth, external IdPs) that don't exist in the sample docs.

2. **Retrieval-only is blindly accurate but hard to use:** It returns exact snippets from docs with no synthesis. User gets facts but must manually connect them. Example: Seeing `generate_access_token` function name doesn't immediately answer "where is it generated"—need to dig into the snippets.

3. **RAG with current guardrail is overly cautious:** It correctly refuses weak-evidence cases (good!), but may refuse valid questions if the evidence is just barely above threshold. Example: Auth token question has real evidence (`generate_access_token`, `AUTH_SECRET_KEY`) but RAG still refuses—indicating the confidence threshold may need tuning.

4. **Hallucination in naive mode increases with complexity:** Simple factual questions (API structure) trigger more hallucination than conceptual ones. The LLM generates plausible-sounding JSON responses that sound authoritative but are invented.

5. **RAG's explicit refusal is a feature, not a bug:** In Cases 2 & 3, refusing to answer is more honest than Retrieval-Only returning irrelevant snippets or Naive LLM guessing.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases I observed:**

**Failure Case 1: Naive LLM Hallucinating JSON Structure**

- **Question:** "What does the /api/projects/<project_id> route return?"
- **What the system did:** Naive LLM generated a detailed JSON response with fields like `status`, `budget`, `owner_id`, `created_at`, `updated_at`, error codes (401, 403, 404, 500), and example timestamps, along with a curl command.
- **What should have happened:** The actual docs mention "/api/projects/<project_id> returns detailed project info" and "404 if the project does not exist," but don't specify the JSON fields. The LLM invented plausible fields that sound correct but are unsupported by evidence. It should either synthesize only from the actual doc text or refuse to answer.

**Failure Case 2: Retrieval-Only Returning Irrelevant Snippets**

- **Question:** "Is there payment processing in the docs?"
- **What the system did:** Retrieval-only mode returned 3 snippets: one about "Using the Docs Assistant (DocuBot)," one about admin users, and one about database migrations.
- **What should have happened:** None of these snippets address payment processing. The system should refuse more explicitly (e.g., "No content about payments was found"), rather than showing snippets that confuse the user into thinking an answer is present.

**When should DocuBot say "I do not know based on the docs I have"?**

1. **When the best-matching paragraph scores below confidence threshold:** Currently set to 1 (needs at least one matching word). If a query has no word overlap with any doc, there's no retrievable evidence.
   - Example: Query "What payment methods are supported?" has no match in docs → refuse.

2. **When retrieved snippets don't address the query:** Even if retrieval returns something, it might be off-topic. The LLM should recognize this and refuse rather than synthesize.
   - Example: Returning database migration snippets for a payment question is noise → refuse.

3. **When the question asks for information outside the scope of the docs:** If a query asks about implementation details, security features, or configurations that the docs don't cover, refuse.
   - Example: "How is the database encrypted at rest?" (not in docs) → refuse.

**What guardrails did you implement?**  

1. **Confidence Threshold (confidence_threshold=1):** Retrieve only returns results if the best-matching paragraph scores >= threshold (i.e., has at least N matching query words). Below threshold, returns empty → system refuses to answer.
   
2. **Explicit Refusal Messages:** Modified answer methods to return clear, honest refusals: "I do not have focused evidence to answer this question. The retrieved sections did not contain enough relevant information." rather than generic "I don't know."
   
3. **Retrieval Before LLM:** RAG calls retrieve() first. If it returns empty (guardrail triggered), LLM is never invoked—we refuse immediately, saving API calls and preventing the LLM from hallucinating on weak data.
   
4. **Source Attribution in Prompts:** LLM is instructed to cite which files it relied on, making evidence explicit and verifiable.

---

## 6. Limitations and Future Improvements

**Current limitations**  

1. **Word-overlap scoring is brittle:** Synonyms and paraphrasing are missed. Query "How do I authenticate?" won't match "authentication" in the docs even though semantically equivalent. Typos also break retrieval.

2. **Paragraph granularity is inconsistent:** Some paragraphs are single-line headers, others are multi-sentence blocks. No semantic understanding of when a paragraph actually answers a question—only word overlap.

3. **Confidence threshold tuning is manual:** The default threshold=1 is a guess. It's overly cautious (refusing valid questions) in some cases and too lenient in others. No automatic calibration based on doc coverage or query complexity.

4. **Guardrail can frustrate users:** Refusing to answer due to weak matches, even when the system *could* synthesize something useful, reduces usability. Trade-off between honesty and helpfulness is hard to get right.

5. **No handling of multi-document context:** If an answer requires combining facts from multiple docs, word-overlap scoring doesn't understand the relationship between snippets.

**Future improvements**  

1. **Semantic similarity scoring:** Replace word-overlap with embeddings (e.g., Sentence-BERT). This would catch paraphrasing, synonyms, and semantic near-matches, improving recall without hallucination.

2. **Adaptive confidence thresholds:** Learn thresholds per query type or doc topic. E.g., authentication questions need 2+ matches; generic questions need 1. Could use calibration on held-out eval set.

3. **Multi-hop reasoning:** For questions that require combining multiple snippets, explicitly detect and synthesize cross-references. Current system treats each snippet independently.

4. **Human-in-the-loop evaluation:** For borderline cases (moderate confidence), show retrieved snippets to a human expert to validate before LLM synthesis. Extends beyond pure automation to hybrid approach.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**

1. **Hallucinated technical details in Naive Mode:** If used in Naive (no-retrieval) mode, the LLM can confidently invent API responses, database schemas, security practices, or endpoint behaviors. A developer following hallucinated docs could build insecure or incompatible code.

2. **False confidence from Retrieval-Only:** Showing snippets without synthesis can mislead users into thinking an answer is present when snippets are noise. Example: A snippet mentioning "projects table" is returned for "What's in the projects endpoint?" but the snippet doesn't actually explain the response format.

3. **RAG Refusals Blocking Valid Questions:** The current guardrail may refuse legitimate questions due to low confidence scores. A frustrated user might then turn to Naive mode (which hallucinates) out of impatience.

4. **Narrow Doc Scope:** If documentation is incomplete or outdated, the system will refuse answers it "should" know, or worse, the docs contain wrong information that the LLM repeats as truth.

**What instructions would you give real developers who want to use DocuBot safely?**

- **Prefer Retrieval-Only for critical facts:** When accuracy is essential (API contracts, security configurations), use Mode 2 and manually verify retrieved snippets rather than trusting LLM synthesis.
  
- **Never use Naive mode for fact checking:** Naive LLM is useful for brainstorming or general explanations, but NOT for looking up specific details in your docs. It will hallucinate confidently.
  
- **Keep documentation current and precise:** DocuBot is only as good as the docs. Maintain clear, up-to-date documentation with concrete examples. Vague or incomplete docs lead to refusals or poor retrieval.
  
- **Review and tune the confidence threshold:** Start with threshold=1, then increase to 2+ if you notice false positives (wrong answers). Decrease below 1 only if you notice too many refusals on valid questions.

---
