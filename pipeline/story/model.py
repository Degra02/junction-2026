"""The embedding model behind story clustering, loaded once at import.

`intfloat/multilingual-e5-small` (MIT): 118M parameters, 384 dimensions, about 100 languages, so
an Italian document and an English report on the same event land close together. It runs on CPU
(D13); the weights (~470 MB) download to `HF_HOME` on the worker's first start.

E5 expects a task prefix. Comparing two news texts is a symmetric task, for which the model card
says to prefix both sides with `query: `.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
PREFIX = "query: "
# Headline and lead decide what event a report is about; longer inputs cost time on 2 vCPU and
# mostly add background paragraphs.
MAX_TOKENS = 256
_BATCH = 16

_model = SentenceTransformer(MODEL, revision=REVISION, device="cpu")
_model.max_seq_length = MAX_TOKENS


def embed(texts: list[str]) -> np.ndarray:
    """Unit-length embeddings, shape `(len(texts), 384)`; cosine similarity is a dot product."""
    if not texts:
        return np.zeros((0, _model.get_sentence_embedding_dimension()), dtype=np.float32)
    return _model.encode(
        [PREFIX + t for t in texts],
        batch_size=_BATCH,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
