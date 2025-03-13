import json
import numpy as np
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans, MiniBatchKMeans


def compute_silhoutte_score_for_cluster(n_cluster: int, sentences: list[str], embeddings: np.ndarray) -> float:
    cluster_assignments = run_kmeans(n_cluster, sentences, embeddings)
    return silhouette_score(embeddings, cluster_assignments)


def run_kmeans(num_clusters: int, sentences: list[str], embeddings: np.ndarray) -> list[int]:
    if len(sentences) == 0:
        return []
    if len(embeddings) < 1025:
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        kmeans.fit(embeddings)
        cluster_assignments = kmeans.labels_
    else:
        kmeans = MiniBatchKMeans(n_clusters=num_clusters, random_state=42)
        for i in range(0, len(embeddings), 1024):
            limit_index = min(i + 1024, len(embeddings))
            batch_embeddings = embeddings[i:limit_index]
            kmeans.partial_fit(batch_embeddings)
            if i == 0:
                cluster_assignments = kmeans.labels_
            else:
                cluster_assignments = np.concatenate((cluster_assignments, kmeans.labels_),
                                                      axis=0)
    return cluster_assignments
