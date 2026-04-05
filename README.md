## Learning Objectives & Challenges

**Core Concept:** The quality of an LLM-based system depends directly on the quality of the evidence fed to it. Naive generation hallucinates freely; retrieval-only is accurate but hard to interpret; RAG balances clarity and grounding—but only if retrieval returns relevant snippets and the LLM respects boundaries. Students need to understand this retrieval-matters principle: *better retrieval = better answers*.

**Common Struggles:** Students often underestimate how hard it is to design good retrieval (choosing paragraph vs. sentence vs. document granularity, tuning scoring functions, deciding when to refuse an answer). They also struggle to recognize when the LLM invents plausible-sounding details that sound confident but aren't in the docs.

**AI as Tool vs. Trap:** Copilot is genuinely helpful for analyzing why two mode outputs differ, exploring scoring strategies, or explaining guardrail tradeoffs. It becomes misleading when it confidently suggests complex solutions (semantic embeddings, neural reranking) without first asking: did you exhaust simple approaches like better chunking or thresholds?

**Guiding Without Spoilers:** Instead of suggesting a solution directly, ask students diagnostic questions: "What retrieval unit size do you think will work best—lines, paragraphs, or whole sections? What's the tradeoff?" or "If RAG refuses valid questions, should you weaken the guardrail, or improve retrieval quality?" Let them reason through the choice.

