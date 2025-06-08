import spacy
from langchain_together import TogetherEmbeddings
from utils.app_config import CONFIG
from sklearn.cluster import DBSCAN, OPTICS
from sklearn.preprocessing import normalize
from joblib import Parallel, delayed
from collections import defaultdict
from utils.convo_utils import compute_silhoutte_score_for_cluster, run_kmeans
from utils.interview_utils import get_chat_model
from sentence_transformers import SentenceTransformer
import numpy as np
import logging
import asyncio
from typing import List
import os

# Set up logging with script name, line number, and timestamp
logging.basicConfig(
    level=logging.DEBUG,  # You can change to INFO or ERROR depending on your needs
    format='%(asctime)s - %(filename)s - Line %(lineno)d - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)

def call_llm(prompt: str, api_key: str, model_name: str) -> str:
    llm = get_chat_model(api_key, model_name)
    response = llm.invoke(prompt).content
    return response

def cluster_sentences(single_transcript: list[dict], api_key: str, use_local: bool=False) -> dict:
    sentences = extract_sentences(single_transcript)
    embeddings = EmbedSentences(api_key, use_local).run(sentences)
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

    def __init__(self, api_key: str, use_local: bool=False):
        self._use_local = use_local
        if not use_local:
            self.model = TogetherEmbeddings(
                model="togethercomputer/m2-bert-80M-32k-retrieval",
                api_key=api_key,
            )
        else:
            self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    async def aembed(self, sentences: list[str]) -> list:
        """Async method to embed sentences with batching support."""
        if not sentences:
            return []
            
        # Batch size to avoid rate limits (adjust based on your specific limits)
        batch_size = 100
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i+batch_size]
            batch_embeddings = await self.model.aembed_documents(batch)
            all_embeddings.extend(batch_embeddings)
            
            # Optional: Add a small delay between batches to avoid rate limits
            if i + batch_size < len(sentences):
                await asyncio.sleep(0.1)
                
        return all_embeddings


    def run(self, sentences: list[str]) -> list:
        if not self._use_local:
            # Run the async method in a synchronous context
            return asyncio.run(self.aembed(sentences))
        embeddings = self.model.encode(sentences, convert_to_numpy=True)
        return embeddings.tolist() 


class ClusterSentences:

    def __init__(self, sentences: list[str], embeddings: list, optimize: bool=False):
        self._sentences = sentences
        self.normalize_embeddings(embeddings)
        self.check_length()
        self._optimize = optimize
    
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
        if not self._optimize:
            cluster_assignments = self.run_kmeans(num_clusters=np.sqrt(len(self._sentences)))
        else:
            max_clusters = min(100, int(1.5*np.sqrt(len(self._sentences))))
            logging.info(f"Optimizing clustering with max clusters {max_clusters}")
            num_clusters = self.find_optimal_cluster_number(max_clusters)
            logging.info(f"Optimized clustering with {num_clusters} clusters")
            cluster_assignments = self.run_kmeans(num_clusters)
        clusters = self.assign_sentences_to_clusters(cluster_assignments)
        return clusters
    
    def run_kmeans(self, num_clusters: int=2) -> list[int]:
        return run_kmeans(num_clusters, self._sentences, self._embeddings)

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
                            user_description: str, api_key: str, model_name: str) -> dict:
    summaries = {}
    for cluster_id, sentences in clusters.items():
        joined_sentences = "\n".join(sentences)
        theme, description, sample_sentences = summarize_sentences(joined_sentences, product_description,
                                      user_description, api_key, model_name)
        if keep_theme(theme, description, product_description, user_description, api_key, model_name):
            summaries[cluster_id] = {
                "theme": theme,
                "description": description,
                "sample_sentences": sample_sentences,
            }
    return summaries
    
def summarize_sentences(sentences: str, product_description: str,
                        user_description: str, api_key: str, model_name: str) -> str:
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
    
    Provide only a concise but complete description of the theme with a summary of the content within these sentences, the theme title, 
    and 2-5 sample sentences from the list above that help support your choice of the theme and the description. 
    Respond in the following format:

    <description> your description here...  </description>
    <theme> your theme title here...  </theme>
    <sample_sentences>
    1. [sample_sentence]
    2. [sample_sentence]
    ...
    </sample_sentences>
    """
    output = call_llm(prompt, api_key, model_name)
    theme = output.split("<theme>")[1].split("</theme>")[0].strip()
    description = output.split("<description>")[1].split("</description>")[0].strip()
    sample_sentences = output.split("<sample_sentences>")[1].split("</sample_sentences>")[0].strip()
    return theme, description, sample_sentences


def keep_theme(theme: str, theme_desc: str, product_description: str, user_description: str, api_key: str, model_name: str) -> bool:
    prompt = f"""An automated analysis platform for user research interviews has discovered the following theme 
    and description based on a cluster of sentences from user interviews for a certain product and user group description.

    Theme: {theme}
    Description: {theme_desc}
    Product Description: {product_description}
    User-group Description: {user_description}

    Your task is to decide if this theme and description is relevant to the product and user group. For instance, some
    themes may be about clusters of introductory sentences or interjections that do not directly relate to user research 
    insights. Take at least 3-5 steps to reason through your answer but take more steps, as needed. 
    Include all of your reasoning within <thinking> tags. Then answer with only TRUE -- if the theme is relevant -- or FALSE --if the theme 
    is irrelevant. For example, 
    
    <thinking>Your reasoning here...</thinking> TRUE/FALSE """
    output = call_llm(prompt, api_key, model_name)
    response = output.split("</thinking>")[1].strip()
    return "TRUE" in response.upper()
