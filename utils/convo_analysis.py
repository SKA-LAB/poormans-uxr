import spacy
from langchain_openai import OpenAIEmbeddings
from utils.app_config import CONFIG
from sklearn.cluster import DBSCAN, OPTICS
from sklearn.preprocessing import normalize
from joblib import Parallel, delayed
from collections import defaultdict
from utils.convo_utils import compute_silhoutte_score_for_cluster, run_kmeans
from utils.interview_utils import get_chat_model
import numpy as np
import logging
import os

# Set up logging with script name, line number, and timestamp
logging.basicConfig(
    level=logging.DEBUG,  # You can change to INFO or ERROR depending on your needs
    format='%(asctime)s - %(filename)s - Line %(lineno)d - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)

def call_llm(prompt: str, api_key: str) -> str:
    llm = get_chat_model(api_key)
    response = llm.invoke(prompt).content
    return response

def cluster_sentences(single_transcript: list[dict], api_key: str) -> dict:
    sentences = extract_sentences(single_transcript)
    embeddings = EmbedSentences(api_key).run(sentences)
    clusters = ClusterSentences(sentences, embeddings).run()
    return clusters

class ExtractSentences:
    """
    Class to extract sentences from a given text.
    """

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")

    def run(self, transcript: str, limit_char: int=10000) -> list[str]:
        if len(transcript) < limit_char:
            sentences = [sent.text for sent in self.nlp(transcript).sents]
            return sentences
        else:
            sentences = []
            for i in range(0, len(transcript), limit_char):
                limit_index = min(i + limit_char, len(transcript))
                batch_transcript = transcript[i:limit_index]
                sentences.extend([sent.text for sent in self.nlp(batch_transcript).sents])
            return sentences


def extract_sentences(single_transcript: list[dict]) -> list[str]:
    extractor = ExtractSentences()
    extracted_sentences = []
    for i,back_and_forth in enumerate(single_transcript):
        user_response = back_and_forth["user"]
        user_sentences = extractor.run(user_response)
        extracted_sentences.extend(user_sentences)
    return extracted_sentences


class EmbedSentences:
    """
    Class to embed sentences using an embedding model.
    """

    def __init__(self, api_key: str):
        self.model = OpenAIEmbeddings(
            model="togethercomputer/m2-bert-80M-32k-retrieval",
            base_url="https://api.together.xyz/v1/embeddings",
            api_key=api_key,
        )

    def run(self, sentences: list[str]) -> list:
        return self.model.embed_documents(sentences)


class ClusterSentences:

    def __init__(self, sentences: list[str], embeddings: list, clustering_method="kmeans", 
                 optimize: bool=False):
        self._sentences = sentences
        self.normalize_embeddings(embeddings)
        self.check_length()
        self._optimize = optimize
        self._clustering_method = clustering_method
    
    def normalize_embeddings(self, embeddings: list) -> None:
        if len(embeddings) > 0:
            self._embeddings = normalize(np.array(embeddings), axis=1, norm='l2')  # normalize to make cosine similarity and euclidean distance directly similar
        else:
            self._embeddings = np.array([])
            logger.warning("No embeddings to normalize")
    
    def check_length(self) -> bool:
        if len(self._sentences) != len(self._embeddings):
            raise ValueError("Number of sentences and embeddings must be equal")
    
    def run(self) -> dict:
        if self._clustering_method == "dbscan":
            cluster_assignments = self.run_dbscan()
        elif self._clustering_method == "optics":
            cluster_assignments = self.run_optics()
        elif self._clustering_method == "kmeans":
            if not self._optimize:
                cluster_assignments = self.run_kmeans(num_clusters=np.sqrt(len(self._sentences)))
            else:
                max_clusters = min(100, int(1.5*np.sqrt(len(self._sentences))))
                logging.info(f"Optimizing clustering with max clusters {max_clusters}")
                num_clusters = self.find_optimal_cluster_number(max_clusters)
                logging.info(f"Optimized clustering with {num_clusters} clusters")
                cluster_assignments = self.run_kmeans(num_clusters)
        else:
            raise ValueError(f"Invalid clustering method: {self._clustering_method}")
        clusters = self.assign_sentences_to_clusters(cluster_assignments)
        return clusters
    
    def run_kmeans(self, num_clusters: int=2) -> list[int]:
        return run_kmeans(num_clusters, self._sentences, self._embeddings)

    def run_dbscan(self, min_samples: int=3, eps: float=0.1) -> list[int]:
        if len(self._sentences) == 0:
            return []
        dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
        dbscan.fit(self._embeddings)
        cluster_assignments = dbscan.labels_
        return cluster_assignments

    def run_optics(self, min_samples: int=3, eps: float=0.1) -> list[int]:
        if len(self._sentences) == 0:
            return []
        optics = OPTICS(eps=eps, min_samples=min_samples, metric="cosine")
        optics.fit(self._embeddings)
        cluster_assignments = optics.labels_
        return cluster_assignments

    def find_optimal_cluster_number(self, max_clusters: int=10) -> int:
        if len(self._sentences) == 0:
            return 0
        if len(self._embeddings) < 2:
            return 1
        step_size = max(1, int(np.round((max_clusters - 2) / 16)))
        silhouette_scores = self.get_silhouette_scores(range(2, max_clusters+1, step_size))
        return self.find_num_clusters(silhouette_scores)
    
    def get_silhouette_scores(self, cluster_range: range, n_jobs: int=4) -> dict:
        results = Parallel(n_jobs=n_jobs)(
            delayed(compute_silhoutte_score_for_cluster)(n_clusters, self._sentences, self._embeddings)
            for n_clusters in cluster_range
        )
        output = {num_clusters: score for num_clusters, score in zip(cluster_range, results)}
        return output
    
    def find_num_clusters(self, silhouette_scores: dict) -> int:
        """silhoutte_scores: {num_clusters: silhouette_score}"""
        max_silhouette_score = max(silhouette_scores.values())
        return next(num_clusters for num_clusters, silhouette_score in silhouette_scores.items() if silhouette_score == max_silhouette_score)

    def assign_sentences_to_clusters(self, cluster_assignments) -> dict:
        clusters = defaultdict(list)
        for idx, cluster_id in enumerate(cluster_assignments):
            clusters[int(cluster_id)].append(self._sentences[idx])
        return clusters



def summarize_each_cluster(clusters: dict, product_description: str,
                            user_description: str, api_key: str) -> dict:
    summaries = {}
    for cluster_id, sentences in clusters.items():
        joined_sentences = "\n".join(sentences)
        theme, description, sample_sentences = summarize_sentences(joined_sentences, product_description,
                                      user_description, api_key)
        summaries[cluster_id] = {
            "theme": theme,
            "description": description,
            "sample_sentences": sample_sentences,
        }
    return summaries
    
def summarize_sentences(sentences: str, product_description: str,
                        user_description: str, api_key: str) -> str:
    prefix = "You are looking at excerpts from transcripts of user interviews.\n"
    if product_description:
        prefix += f"For the following product description: {product_description}\n"
    if user_description:
        prefix += f"And the following general user description: {user_description}\n"
    prompt = f"""{prefix}
    The following sentences were clustered together across different user interviews.
    Your task is to find a title and a description of a single theme that connects these sentences. 
    
    SENTENCES:
    {sentences}
    
    Provide only the theme, a short description, and some sample sentences from the list above that help
    support your choice of the theme and the description. Here is the response format
    
    Theme: [theme]
    Description: [description]
    Sample Sentences: [sample_sentences]
    """
    output = call_llm(prompt, api_key)
    theme, rest = output.split("Description: ")
    description, sample_sentences = rest.split("Sample Sentences: ")
    theme = theme.split("Theme")[-1].strip()
    return theme, description, sample_sentences

def find_all_representative_sentences(self, number: int, summaries: dict, clusters: dict) -> dict:
    return None  # TODO: Implement this function to find the most representative sentences from the cluster summaries

def find_representative_sentences(self, number: int, summary_text: str, sentences: list[str]) -> list[str]:
    return None  # TODO: Implement this function to find the most representative sentences from the cluster summary


    
