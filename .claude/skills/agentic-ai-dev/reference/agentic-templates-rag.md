# Agentic AI RAG Architectures

Six production-ready RAG patterns from simple to advanced, plus document ingestion pipeline.

## Pattern 1: Standard RAG

Baseline retrieve → **code evidence gate** → generate. Empty retrieval is `INSUFFICIENT_EVIDENCE` and **must not call the model**. A prompt that says "I don't have enough information" is not the gate (`tool-execution-safety.md`).

Executed (langchain 1.5.2 / langgraph 1.2.24, scripted model that always answers `"42"`): empty retriever → `INSUFFICIENT_EVIDENCE`, `answer=""`, model call count 0; one in-scope doc → `OK` and the model ran once. Tenant isolation is **not** a LangChain primitive: `org_id` is required on state (from the verified principal, never the model), the retriever must filter by that id, and `retrieve` drops any doc whose `metadata.acl` is missing or does not match (executed: untagged doc → `INSUFFICIENT_EVIDENCE`, model not called).

```python
from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from ...core.logging import get_logger

logger = get_logger(__name__)

RAGStatus = Literal["OK", "INSUFFICIENT_EVIDENCE"]


class StandardRAGState(TypedDict):
    query: str
    org_id: str
    docs: list[str]
    doc_ids: list[str]
    status: RAGStatus
    answer: str


class Retriever(Protocol):
    def invoke(self, query: str, *, org_id: str) -> list[Any]: ...


def evidence_status(docs: list[str]) -> RAGStatus:
    """Deterministic gate: model text cannot override this."""
    return "OK" if any(d.strip() for d in docs) else "INSUFFICIENT_EVIDENCE"


def build_standard_rag(llm, retriever: Retriever, reranker=None):
    """Retrieve → gate → generate. The LLM never sees an empty context."""

    def retrieve(state: StandardRAGState) -> dict[str, Any]:
        org_id = state.get("org_id") or ""
        if not org_id:
            raise PermissionError("org_id required")
        docs = retriever.invoke(state["query"], org_id=org_id)
        if reranker:
            docs = reranker.compress_documents(docs, state["query"])
        contents: list[str] = []
        doc_ids: list[str] = []
        for d in docs:
            meta = getattr(d, "metadata", None) or {}
            if meta.get("acl") != org_id:
                continue
            contents.append(d.page_content if hasattr(d, "page_content") else str(d))
            if meta.get("id"):
                doc_ids.append(str(meta["id"]))
        status = evidence_status(contents)
        logger.info("rag_retrieved", doc_count=len(contents), status=status)
        update: dict[str, Any] = {"docs": contents, "doc_ids": doc_ids, "status": status}
        if status != "OK":
            update["answer"] = ""
        return update

    def generate(state: StandardRAGState) -> dict[str, Any]:
        if evidence_status(state["docs"]) != "OK":
            return {"status": "INSUFFICIENT_EVIDENCE", "answer": ""}
        context = "\n\n".join(state["docs"])
        msg = llm.invoke(
            [
                {
                    "role": "system",
                    "content": "Answer using ONLY the context. Do not invent facts.",
                },
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {state['query']}"},
            ]
        )
        text = msg.content if hasattr(msg, "content") else str(msg)
        return {"answer": text, "status": "OK"}

    def after_retrieve(state: StandardRAGState):
        return "generate" if state["status"] == "OK" else END

    g = StateGraph(StandardRAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", after_retrieve, ["generate", END])
    g.add_edge("generate", END)
    return g.compile()
```

## Pattern 2: Agentic RAG

Query routing + document grading + web search fallback. The agent decides whether to search the knowledge base, web, or both.

```python
from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..state import RAGState
from ...core.logging import get_logger

logger = get_logger(__name__)


class RouteDecision(BaseModel):
    """Structured output for query routing."""
    source: Literal["vectorstore", "web_search"] = Field(
        description="Route to vectorstore for domain questions, web_search for current events"
    )


class GradeDocuments(BaseModel):
    """Grade whether a document is relevant to the query."""
    is_relevant: Literal["yes", "no"] = Field(description="Is this document relevant to the query?")


def build_agentic_rag(llm, retriever, web_search_tool, checkpointer=None):
    """Build an agentic RAG graph with query routing and document grading."""

    structured_router = llm.with_structured_output(RouteDecision)
    structured_grader = llm.with_structured_output(GradeDocuments)

    async def route_query_node(state: RAGState) -> dict:
        """Route query to vectorstore or web search."""
        query = state["messages"][-1].content
        decision = await structured_router.ainvoke([
            {"role": "system", "content": "Route this query to 'vectorstore' for domain knowledge or 'web_search' for current events."},
            {"role": "user", "content": query},
        ])
        logger.info("rag_route", source=decision.source, query_len=len(query))
        return {"query": query}

    async def retrieve_node(state: RAGState) -> dict:
        """Retrieve documents from vector store."""
        docs = await retriever.ainvoke(state["query"])
        return {"documents": [{"content": d.page_content, "metadata": d.metadata} for d in docs]}

    async def grade_documents_node(state: RAGState) -> dict:
        """Grade retrieved documents for relevance."""
        relevant_docs = []
        for doc in state["documents"]:
            grade = await structured_grader.ainvoke([
                {"role": "system", "content": "Grade whether this document is relevant to the query."},
                {"role": "user", "content": f"Query: {state['query']}\nDocument: {doc['content'][:500]}"},
            ])
            if grade.is_relevant == "yes":
                relevant_docs.append(doc)

        logger.info("rag_graded", total=len(state["documents"]), relevant=len(relevant_docs))
        return {"documents": relevant_docs}

    async def web_search_node(state: RAGState) -> dict:
        """Fall back to web search when vectorstore results are insufficient."""
        results = await web_search_tool.ainvoke(state["query"])
        web_docs = [{"content": r, "metadata": {"source": "web"}} for r in results]
        return {"documents": [*state["documents"], *web_docs]}

    async def generate_node(state: RAGState) -> dict:
        """Generate only when documents exist. Untrusted context is user content, not system."""
        docs = state.get("documents") or []
        if not docs:
            return {"status": "INSUFFICIENT_EVIDENCE", "generation": ""}
        context = "\n\n".join(doc["content"] for doc in docs)
        response = await llm.ainvoke([
            {"role": "system", "content": "Answer using ONLY the user-supplied context. Do not invent facts."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {state['query']}"},
        ])
        return {"messages": [response], "generation": response.content, "status": "OK"}

    def decide_after_grading(state: RAGState) -> Literal["generate", "web_search"]:
        """If no relevant docs found, fall back to web search."""
        if not state["documents"]:
            return "web_search"
        return "generate"

    def after_web(state: RAGState) -> Literal["generate", "__end__"]:
        return "generate" if state.get("documents") else "__end__"

    # --- Graph ---
    graph = StateGraph(RAGState)
    graph.add_node("route", route_query_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", grade_documents_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("route")
    graph.add_edge("route", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", decide_after_grading)
    graph.add_conditional_edges("web_search", after_web, ["generate", END])
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer)
```

## Pattern 3: Self-RAG

Generation grading + hallucination check loop. The agent evaluates its own output.

```python
class HallucinationGrade(BaseModel):
    """Check if generation is grounded in documents."""
    is_grounded: Literal["yes", "no"] = Field(description="Is the answer supported by the documents?")


class AnswerGrade(BaseModel):
    """Check if generation actually answers the question."""
    is_useful: Literal["yes", "no"] = Field(description="Does this answer address the question?")


def build_self_rag(llm, retriever, checkpointer=None):
    """Self-RAG: generate, check hallucination, check usefulness, retry if needed."""

    grounded_checker = llm.with_structured_output(HallucinationGrade)
    answer_checker = llm.with_structured_output(AnswerGrade)

    async def check_hallucination_node(state: RAGState) -> dict:
        context = "\n".join(doc["content"] for doc in state["documents"])
        grade = await grounded_checker.ainvoke([
            {"role": "system", "content": "Is this answer grounded in the documents?"},
            {"role": "user", "content": f"Documents:\n{context}\n\nAnswer:\n{state['generation']}"},
        ])
        return {"is_grounded": grade.is_grounded == "yes"}

    async def check_answer_node(state: RAGState) -> dict:
        grade = await answer_checker.ainvoke([
            {"role": "system", "content": "Does this answer address the original question?"},
            {"role": "user", "content": f"Question: {state['query']}\nAnswer: {state['generation']}"},
        ])
        if grade.is_useful == "no":
            return {"messages": [AIMessage(content="Let me search for more information...")]}
        return {}

    def hallucination_router(state: RAGState) -> str:
        if not state["is_grounded"]:
            logger.warning("hallucination_detected", query_len=len(state["query"]))
            return "retrieve"  # Re-retrieve and regenerate
        return "check_answer"

    # Compose into graph with: retrieve → grade → generate → check_hallucination → check_answer → END
```

## Pattern 4: Graph RAG

Entity-relationship queries using a graph database (Neo4j).

```python
async def graph_rag_retrieve(query: str, graph_db, llm) -> list[dict]:
    """Use LLM to generate Cypher query, then retrieve from Neo4j."""
    cypher_prompt = f"""Generate a Cypher query for Neo4j to answer: {query}
    Schema: (Person)-[:WORKS_AT]->(Company), (Person)-[:KNOWS]->(Person)
    Return ONLY the Cypher query."""

    cypher = await llm.ainvoke([{"role": "user", "content": cypher_prompt}])
    results = graph_db.query(cypher.content)
    return [{"content": str(r), "metadata": {"source": "graph_db"}} for r in results]
```

## Pattern 5: HyDE RAG

Hypothetical Document Embeddings — generate a hypothetical answer, embed it, use for retrieval.

```python
async def hyde_retrieve(query: str, llm, embeddings, vector_store) -> list:
    """HyDE: Generate hypothetical document, use its embedding for retrieval."""
    # Step 1: Generate hypothetical answer
    hypothetical = await llm.ainvoke([
        {"role": "system", "content": "Write a detailed paragraph that would answer this question."},
        {"role": "user", "content": query},
    ])

    # Step 2: Embed the hypothetical document
    hyde_embedding = await embeddings.aembed_query(hypothetical.content)

    # Step 3: Search vector store with hypothetical embedding
    docs = vector_store.similarity_search_by_vector(hyde_embedding, k=5)
    logger.info("hyde_retrieved", doc_count=len(docs))
    return docs
```

## Pattern 6: Multi-Step RAG

Query decomposition + parallel retrieval for complex questions.

```python
class QueryDecomposition(BaseModel):
    """Decompose a complex query into sub-queries."""
    sub_queries: list[str] = Field(min_length=1, max_length=4, description="2–4 simpler sub-queries")


async def multi_step_retrieve(query: str, llm, retriever) -> list:
    """Decompose query → parallel retrieval → merge results."""
    import asyncio

    # Step 1: Decompose
    decomposer = llm.with_structured_output(QueryDecomposition)
    decomposition = await decomposer.ainvoke([
        {"role": "system", "content": "Break this complex question into 2-4 simpler sub-questions."},
        {"role": "user", "content": query},
    ])

    # Step 2: Parallel retrieval
    tasks = [retriever.ainvoke(sq) for sq in decomposition.sub_queries]
    all_results = await asyncio.gather(*tasks)

    # Step 3: Deduplicate and merge
    seen_ids = set()
    merged = []
    for docs in all_results:
        for doc in docs:
            doc_id = doc.metadata.get("id", doc.page_content[:100])
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged.append(doc)

    logger.info("multi_step_retrieved", sub_queries=len(decomposition.sub_queries), total_docs=len(merged))
    return merged
```

`asyncio.gather` here is cheap read-only retrieval inside one node (schema already caps width). Use `Send` when each sub-query is an expensive/resumable model call (`agentic-templates-advanced.md` Pattern 7). Empty `merged` must not reach the generator as success: typed `INSUFFICIENT_EVIDENCE` regardless of model text (`tool-execution-safety.md` evidence gate; Pattern 1 implements this in `retrieve` before `generate`).

Production controls this file does not duplicate: hybrid/keyword+vector search, metadata/ACL filters, tenant isolation, citations and grounding, corrective RAG — `rag-architect` and `vector-database`.

## Document Ingestion Pipeline

**File:** `src/<service>/rag/indexing/pipeline.py`

```python
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredHTMLLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter


def build_ingestion_pipeline(embeddings, vector_store):
    """Build a document ingestion pipeline: load → split → embed → index."""

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    loaders = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".html": UnstructuredHTMLLoader,
    }

    async def ingest(file_path: str, metadata: dict | None = None) -> int:
        """Ingest a document into the vector store.

        Returns:
            Number of chunks indexed.
        """
        ext = "." + file_path.rsplit(".", 1)[-1].lower()
        loader_cls = loaders.get(ext)
        if not loader_cls:
            raise ValueError(f"Unsupported file type: {ext}")

        docs = loader_cls(file_path).load()

        # Add metadata
        if metadata:
            for doc in docs:
                doc.metadata.update(metadata)

        chunks = splitter.split_documents(docs)
        await vector_store.aadd_documents(chunks)

        logger.info("ingestion_complete", file=file_path, chunks=len(chunks))
        return len(chunks)

    return ingest
```

## RAG Selection Guide

| Pattern | Use When | Complexity | Quality |
|---------|----------|------------|---------|
| Standard RAG | Simple Q&A over documents | Low | Good |
| Agentic RAG | Need routing + fallback | Medium | Better |
| Self-RAG | Hallucination is unacceptable | Medium | Best |
| Graph RAG | Entity-relationship queries | High | Best for structured data |
| HyDE RAG | Short/ambiguous queries | Medium | Better retrieval |
| Multi-Step RAG | Complex multi-part questions | Medium | Best for complex queries |
