import hashlib
import streamlit as st

# Placeholder for LLM interaction
def call_llm(prompt):
    """
    Calls an LLM API with the given prompt.
    Replace this with your actual LLM API call.
    """
    # st.write(f"DEBUG: LLM Prompt: {prompt}")  # For debugging

    # --- REPLACE THIS WITH YOUR ACTUAL LLM API CALL ---
    # Example (using a dummy response):
    response = "This is a simulated LLM response to: " + prompt
    return response

def md5_hash(text):
    return hashlib.md5(text.encode()).hexdigest()

# --- SIMULATED VECTOR DATABASE --- (Replace with a real vector database)
_vector_db = {}

def embed_sentence(sentence):
    """Simulates embedding a sentence."""
    # In a real application, use a sentence embedding model (e.g., Sentence Transformers)
    sentence_hash = md5_hash(sentence)
    if sentence_hash not in _vector_db:
      _vector_db[sentence_hash] = [float(ord(c)) for c in sentence_hash] # Very basic vector representation
    return _vector_db[sentence_hash]

def find_similar_sentences(embedding, threshold=0.8):
    """Simulates finding similar sentences based on embeddings."""
    # In a real application, use a vector database's similarity search.

    similar_sentences = []
    for stored_hash, stored_embedding in _vector_db.items():
        #Very simple cosine
        similarity = sum(a * b for a, b in zip(embedding, stored_embedding)) / (
            (sum(a * a for a in embedding) ** 0.5) * (sum(b * b for b in stored_embedding) ** 0.5)
        )
        if similarity > threshold:
            similar_sentences.append(stored_hash)
    return similar_sentences

def cluster_sentences(sentences):
    """Simulates clustering sentences."""
    # Basic clustering, replace by k-means or other methods
    clusters = {}
    cluster_id = 0
    for sentence in sentences:
        embedding = embed_sentence(sentence)
        similar = find_similar_sentences(embedding)
        if len(similar) == 0:
            clusters[cluster_id] = [sentence]
            cluster_id += 1
        else:
            clusters[cluster_id-1].append(sentence)
    return clusters