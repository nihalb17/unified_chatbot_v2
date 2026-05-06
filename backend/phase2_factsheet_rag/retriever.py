import os
from embedder import get_chroma_client, embed_texts

def retrieve_chunks(query: str, n_results: int = 5, where: dict = None) -> list[dict]:
    """
    Retrieve relevant chunks for a given query from ChromaDB.
    Uses local embeddings (via embedder.embed_texts).
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection("factsheet_kb")
    except Exception as e:
        print(f"[Retriever] Error getting collection: {e}")
        return []
    
    # Generate query embedding locally (using Gemini retrieval_query type)
    query_embeddings = embed_texts([query], task_type="retrieval_query")
    if not query_embeddings:
        return []
    
    query_embedding = query_embeddings[0]
    
    # Query Chroma
    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        print(f"[Retriever] Query error: {e}")
        return []
        
    chunks = []
    if results and results["ids"] and len(results["ids"][0]) > 0:
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i] if "distances" in results else None
            chunks.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": distance
            })
            
    return chunks
