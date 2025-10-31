import os
import torch
from sentence_transformers import SentenceTransformer
from rag.index import load_embeddings_and_docs, build_and_save_embeddings
from rag.util import answerWithRAG
from pathlib import Path

def test_rag(query):
    """
    Test the RAG retrieval and response functions.
    """
    print("=" * 60)
    print("[TEST] Starting RAG Functionality Test")
    print("=" * 60)

    # Make sure RAGData exists
    if not os.path.exists("rag_date"):
        os.makedirs("rag_date", exist_ok=True)

    # Step 1: Build if the embeddings do not exist
    emb_path = os.path.join("rag_date", "embeddings.npy")
    docs_path = os.path.join("rag_date", "docs.pkl")

    if not os.path.exists(emb_path) or not os.path.exists(docs_path):
        print("[INFO] Embeddings not found, building new ones...")
        build_and_save_embeddings()
    else:
        print("[INFO] Embeddings found, skipping build step.")

    # Step 2: Load vector library
    print("[INFO] Loading embeddings and documents...")
    embeddings_np, docs, docsDict = load_embeddings_and_docs()
    embeddings = torch.tensor(embeddings_np)

    # Step 3: Load model
    print("[INFO] Loading embedding model...")
    model_path = Path(__file__).parent / "models" / "mxbai-embed-large-v1"

    # Key: Switch to the absolute path
    model_path = model_path.resolve()

    print("[DEBUG] Using absolute model path:", model_path)

    embeddingModel = SentenceTransformer(str(model_path))

    # Step 4: Questions and perform the RAG retrieval
    print("=" * 60)
    print(f"[QUERY] {query}")
    print("=" * 60)
    answer = answerWithRAG(query, embeddings, embeddingModel, docs, docsDict)

    # Step 5: Output results
    print("\n[ANSWER CONTEXT]")
    print("-" * 60)
    print(answer if answer else "No relevant context found.")
    print("-" * 60)

    print("[TEST] RAG test completed successfully.")


if __name__ == "__main__":
    # You can freely modify the query to test different questions
    test_rag("Please analyze the data and provide insights on:1. Key patterns in successful vs unsuccessful runs.2. Parameter ranges that appear promising.3. Any timing or wirelength trends.4. Recommendations for subsequent runs.")
