"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        Build an inverted index mapping lowercase words to (filename, paragraph_id) tuples.
        
        This enables fine-grained retrieval: instead of indexing whole documents,
        we index paragraphs (newline-separated blocks). This helps the retrieval logic
        identify small, focused sections rather than returning massive files.
        
        Structure:
        {
            "token": [("AUTH.md", 0), ("AUTH.md", 2), ("API_REFERENCE.md", 1)],
            "database": [("DATABASE.md", 3)]
        }
        """
        index = {}
        for filename, text in documents:
            paragraphs = text.split('\n')
            for para_id, paragraph in enumerate(paragraphs):
                words = paragraph.lower().split()
                for word in words:
                    word = word.strip('.,!?;:"\'')
                    if word:
                        if word not in index:
                            index[word] = []
                        # Store (filename, para_id) so we can retrieve specific paragraphs
                        if (filename, para_id) not in index[word]:
                            index[word].append((filename, para_id))
        return index

    # -----------------------------------------------------------
    # Paragraph Extraction Helper
    # -----------------------------------------------------------

    def get_paragraph(self, filename, para_id):
        """
        Retrieve a specific paragraph (by index) from a document.
        Returns the paragraph text or empty string if not found.
        """
        for doc_filename, text in self.documents:
            if doc_filename == filename:
                paragraphs = text.split('\n')
                if 0 <= para_id < len(paragraphs):
                    return paragraphs[para_id]
                return ""
        return ""

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        query_words = query.lower().split()
        query_words = [word.strip('.,!?;:"\'') for word in query_words if word.strip('.,!?;:"\'')]
        text_lower = text.lower()
        score = 0
        for word in query_words:
            if word in text_lower:
                score += 1
        return score

    def retrieve(self, query, top_k=3, confidence_threshold=1):
        """
        Retrieve top_k most relevant text snippets based on query.
        
        Now works at paragraph granularity instead of whole documents.
        Each paragraph is a newline-separated block, enabling finer-grained retrieval.
        
        Args:
            query: user question
            top_k: number of paragraphs to return
            confidence_threshold: minimum score required to return any results.
                If best score < threshold, returns empty list (guardrail).
        
        Returns:
            List of (filename, paragraph_text) tuples, sorted by relevance.
            
        Guardrail Logic:
            If the highest-scoring paragraph scores below confidence_threshold,
            no results are returned. This prevents answering when we have weak evidence.
        """
        query_words = query.lower().split()
        query_words = [word.strip('.,!?;:"\'') for word in query_words if word.strip('.,!?;:"\'')]
        
        if not query_words:
            return []  # Empty query → no results
        
        # Get candidate (filename, para_id) pairs from index
        candidate_paragraphs = set()
        for word in query_words:
            if word in self.index:
                candidate_paragraphs.update(self.index[word])
        
        # Score each candidate paragraph
        scored_paragraphs = []
        for filename, para_id in candidate_paragraphs:
            paragraph_text = self.get_paragraph(filename, para_id)
            if paragraph_text.strip():  # Only score non-empty paragraphs
                score = self.score_document(query, paragraph_text)
                scored_paragraphs.append((score, filename, para_id, paragraph_text))
        
        if not scored_paragraphs:
            return []
        
        # Sort by score descending
        scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
        
        # GUARDRAIL: Check if best score meets confidence threshold
        best_score = scored_paragraphs[0][0]
        if best_score < confidence_threshold:
            # Weak evidence - refuse to answer
            return []
        
        # Return top_k as (filename, text)
        results = [(filename, paragraph_text) 
                   for score, filename, para_id, paragraph_text in scored_paragraphs[:top_k]]
        return results

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        
        If no snippets meet the confidence threshold, explicitly refuses to answer.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not have focused evidence to answer this question. The retrieved sections did not contain enough relevant information."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        
        If no snippets meet the confidence threshold, refuses to answer before
        even calling the LLM.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not have focused evidence to answer this question. The retrieved sections did not contain enough relevant information."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
