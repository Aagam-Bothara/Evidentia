"""Embedding service — generates text embeddings using sentence-transformers."""

from __future__ import annotations

from evidentia.core.logging import get_logger

logger = get_logger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment, misc]

_INSTALL_MSG = (
    "sentence-transformers is required for vector search. "
    "Install it with: pip install evidentia[retrieval]"
)


class EmbeddingService:
    """Generates text embeddings using sentence-transformers.

    Wraps the sentence-transformers library to provide a simple interface
    for single-text and batch embedding. The model is loaded lazily on
    first use and cached for subsequent calls.

    Raises ``RuntimeError`` at init time if sentence-transformers is not
    installed, with a clear instruction on how to install it.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        if SentenceTransformer is None:
            raise RuntimeError(_INSTALL_MSG)

        self._model_name = model_name
        self._model: SentenceTransformer | None = None  # type: ignore[no-any-unimported]
        logger.info("embedding_service_init", model_name=model_name)

    def _load_model(self) -> SentenceTransformer:  # type: ignore[no-any-unimported]
        """Lazy-load the model on first embed call."""
        if self._model is None:
            logger.info("embedding_model_loading", model_name=self._model_name)
            self._model = SentenceTransformer(self._model_name)  # type: ignore[misc]
            logger.info(
                "embedding_model_loaded",
                model_name=self._model_name,
                dimension=self.dimension,
            )
        return self._model

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()  # type: ignore[union-attr]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch.

        Batching is significantly more efficient than embedding texts
        one at a time because the model can parallelise the computation.

        Args:
            texts: List of text strings to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        if not texts:
            return []

        model = self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        logger.debug("batch_embedded", count=len(texts))
        return [v.tolist() for v in vectors]

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Loads the model if it has not been loaded yet.
        """
        model = self._load_model()
        return model.get_sentence_embedding_dimension()  # type: ignore[return-value]
