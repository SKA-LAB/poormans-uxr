from utils.persona_archetypes import archetypes
from utils.app_config import CONFIG
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
import logging
import dotenv
import os

dotenv.load_dotenv()

# Set up logging with script name, line number, and timestamp
logging.basicConfig(
    level=logging.DEBUG,  # You can change to INFO or ERROR depending on your needs
    format='%(asctime)s - %(filename)s - Line %(lineno)d - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


def generate_archetype(product_desc: str, user_group_desc: str, llm="")


class PersonaGenerator:

    def __init__(self, llm="llama3.1", verbose=False):
        self.archetypes = archetypes
        self.llm = self.set_lc_lm(llm)
        self.verbose = verbose

    def set_lc_lm(self, llm="llama3.1"):
        return ChatOllama(
            model=CONFIG[llm],
            temperature=CONFIG["llm_temp"],
            base_url=CONFIG["route"],
            api_key=CONFIG["api_key"],
            num_ctx=16000,
        )

    def get_archetype_names(self):
        return list(self.archetypes.keys())

    def generate_persona(self, archetype_name: list[str]) -> str:
        if not archetype_name:
            logger.error("No archetype provided.")
            return "No archetype provided."

        persona_text = ""
        for archetype in archetype_name:
            if archetype in self.archetypes:
                persona_text += self.archetypes[archetype] + "\n\n"
            else:
                logger.warning(f"Archetype '{archetype}' not found.")

        prompt = self.get_prompt(persona_text)
        output = self.llm.invoke(prompt).content
        if self.verbose:
            logger.debug(f"Generated response: {output}")
        return output


    def get_prompt(self, persona_text: str) -> str:
        prompt = f"""Given the following 1 or more surgeon persona archetypes, generate a clear, complete, and well-structured surgeon persona with the following requirements:

        - Name: The name of the surgeon.
        - Age: The age of the surgeon.
        - Specialty: The specialty of the surgeon.
        - Expertise: The expertise and knowledge of the surgeon.
        - Demographics: The demographics of the surgeon (e.g., gender, race, ethnicity).
        - Location: The location of the surgeon.
        - Motivations: The motivations and goals of the surgeon.
        - Goals and needs: The goals and needs of the surgeon.
        - Values: The values and aspirations of the surgeon.
        - Attitudes and beliefs: The attitudes and beliefs of the surgeon.
        - Lifestyle: The lifestyle of the surgeon.
        - Daily routine: The daily routine of the surgeon.
        - Devise usage: The usage of technology by the surgeon.
        - Software familiarity: Their level of comfort with specific software or platforms?
        - Digital literacy: Confidence in navigating digital platforms and software.
        - Pain points: The pain points and concerns of the surgeon.
        - Delightful moments: The moments and experiences that bring the surgeon joy and satisfaction.

        SURGEON PERSONA ARCHETYPE(S): 
        {persona_text}

        Provide only the persona in your response.
        """
        return prompt