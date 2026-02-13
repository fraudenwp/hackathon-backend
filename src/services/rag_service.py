"""
RAG Service - ChromaDB + LangChain text splitting for document search
Uses fal.ai OpenRouter embeddings API for high-quality multilingual embeddings.
"""

import httpx
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.constants.env import CHROMA_PERSIST_DIR, FAL_API_KEY
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_ENDPOINT = "https://fal.run/openrouter/router/openai/v1/embeddings"


class FalEmbeddingFunction(EmbeddingFunction):
    """ChromaDB embedding function using fal.ai OpenRouter embeddings API"""

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL):
        self._api_key = api_key
        self._model = model
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
        )

    def __call__(self, input: Documents) -> Embeddings:
        response = self._client.post(
            EMBEDDING_ENDPOINT,
            json={"input": input, "model": self._model},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


class RagService:
    """Document embedding and retrieval service using ChromaDB"""

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedding_fn = FalEmbeddingFunction(api_key=FAL_API_KEY)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        logger.info("RagService initialized", persist_dir=persist_dir, model=EMBEDDING_MODEL)

    def _get_collection(self, user_id: str) -> chromadb.Collection:
        """Get or create a user-scoped collection"""
        return self._client.get_or_create_collection(
            name=f"user_{user_id}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedding_fn,
        )

    def add_document(self, user_id: str, doc_id: str, text: str, filename: str = "") -> int:
        """Chunk text and add to user's ChromaDB collection. Returns chunk count."""
        try:
            collection = self._get_collection(user_id)
            chunks = self._splitter.split_text(text)

            if not chunks:
                logger.warning("No chunks generated", doc_id=doc_id)
                return 0

            ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
            metadatas = [{"doc_id": doc_id, "chunk_index": i, "filename": filename} for i in range(len(chunks))]

            collection.add(
                documents=chunks,
                ids=ids,
                metadatas=metadatas,
            )

            logger.info(
                "Document embedded",
                doc_id=doc_id,
                user_id=user_id,
                chunk_count=len(chunks),
            )
            return len(chunks)

        except Exception as e:
            log_error(logger, "Failed to embed document", e, doc_id=doc_id)
            raise

    def search(self, user_id: str, query: str, k: int = 3, doc_ids: list[str] | None = None) -> list[dict]:
        """Search user's documents. Optionally filter by doc_ids. Returns list of {text, doc_id, score}."""
        try:
            collection = self._get_collection(user_id)

            if collection.count() == 0:
                return []

            where_filter = None
            if doc_ids:
                where_filter = {"doc_id": {"$in": doc_ids}}

            results = collection.query(
                query_texts=[query],
                n_results=min(k, collection.count()),
                where=where_filter,
            )

            items = []
            for i in range(len(results["documents"][0])):
                items.append({
                    "text": results["documents"][0][i],
                    "doc_id": results["metadatas"][0][i]["doc_id"],
                    "score": results["distances"][0][i] if results.get("distances") else None,
                })

            return items

        except Exception as e:
            log_error(logger, "RAG search failed", e, user_id=user_id)
            return []

    def delete_document(self, user_id: str, doc_id: str) -> None:
        """Delete all chunks for a document from user's collection"""
        try:
            collection = self._get_collection(user_id)
            collection.delete(where={"doc_id": doc_id})
            logger.info("Document chunks deleted", doc_id=doc_id, user_id=user_id)
        except Exception as e:
            log_error(logger, "Failed to delete document chunks", e, doc_id=doc_id)

    def list_documents(self, user_id: str, doc_ids: list[str] | None = None) -> list[dict]:
        """List unique documents for a user. Optionally filter by doc_ids. Returns [{doc_id, filename}]."""
        try:
            collection = self._get_collection(user_id)
            if collection.count() == 0:
                return []
            all_meta = collection.get(include=["metadatas"])
            docs: dict[str, str] = {}  # doc_id -> filename
            for m in all_meta.get("metadatas", []):
                if m and m.get("doc_id"):
                    did = m["doc_id"]
                    if doc_ids and did not in doc_ids:
                        continue
                    if did not in docs:
                        docs[did] = m.get("filename", did)
            return [{"doc_id": did, "filename": fn} for did, fn in docs.items()]
        except Exception:
            return []

    def has_documents(self, user_id: str) -> bool:
        """Check if user has any embedded documents"""
        try:
            collection = self._get_collection(user_id)
            return collection.count() > 0
        except Exception:
            return False


# Singleton
rag_service = RagService()
