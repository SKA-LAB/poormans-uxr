from langchain_openai import ChatOpenAI
import json
import glob
import datetime
from timeit import default_timer as timer

def get_general_cot_prompt() -> str:
    prompt = """Before asking or answering questions, reason through the conversation so far and think about how you 
    would respond or continue the conversation based on your persona and characteristics. Take at least 3 steps to reason 
    but take more steps, as needed. Once you are ready, then respond. 

    Format your output as:
    <thinking>Your reasoning here...</thinking>
    <response>Your response here...</response>
    """
    return prompt

def parse_response(response: str) -> str:
    response = response.split("<response>")[1].split("</response>")[0].strip()
    return response

def get_researcher_persona():
    name = "Roxy Buttons"
    desc = """You are an experienced user researcher specializing in identifying user needs
    and understanding user behavior. Your goal is to ask thoughtful, open-ended questions
    that uncover the user's motivations, challenges, and potential value propositions 
    for using a product or service."""
    return name, desc

def get_chat_model(api_key: str, model_name: str="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free") -> ChatOpenAI:
    return ChatOpenAI(model=model_name,
                    base_url="https://api.together.xyz/v1/",
                    temperature=0.7,
                    api_key=api_key)

def simulate_interview(uxr_persona_name: str, uxr_persona_desc: str, persona_name: str, 
                       persona_desc: str, product_desc: str, api_key: str, turns: int=5,
                       model_name: str="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"):
    researcher_chat = get_chat_model(api_key, model_name)
    user_chat = get_chat_model(api_key, model_name)
    cot_prompt = get_general_cot_prompt()

    # Define the user researcher persona
    user_researcher_persona =f"""Your are the following persona:
        Name:{uxr_persona_name}
        Description: {uxr_persona_desc}
        
        You are currently gathering information and conducting interviews for a product focused 
        on {product_desc}. Your primary goal is to understand the value proposition of this product and explore the 
        problem space more completely. You are tasked with interviewing people who may be users of this product.
        
        You are interviewing someone right now. {cot_prompt}"""
    
    # Define the user persona
    user_persona = f"""Your are the following persona:
        Name: {persona_name}
        Description: 
        {persona_desc}
        
        You are currently being interviewed by a user researcher. {cot_prompt}"""
    
    # Start the conversation
    conv_ux_perspective = [
        ("system", user_researcher_persona),
        ("human", "Let's begin the interview."),
    ]

    conv_user_perspective = [
        ("system", user_persona),
    ]

    # Simulate the conversation
    conversation_history = simulate_conversation(researcher_chat, user_chat, conv_ux_perspective, conv_user_perspective, turns=5)
    return conversation_history

# Function to simulate the conversation between the two personas
def simulate_conversation(researcher_chat, user_chat, conv_ux_perspective, conv_user_perspective, turns=5):
    conversation_history = []
    for _ in range(turns):
        # Researcher asks a question
        researcher_response = parse_response(researcher_chat.invoke(conv_ux_perspective).content)
        print(f"Researcher: {researcher_response}\n")
        conv_ux_perspective.append(("assistant", researcher_response))

        # add the researcher output to the user conversation perspective
        conv_user_perspective.append(("human", researcher_response))
        
        # User responds to the question
        user_response = parse_response(user_chat.invoke(conv_user_perspective).content)
        print(f"User: {user_response}\n")
        conv_user_perspective.append(("assistant", user_response))

        # add the user output to the researcher conversation perspective
        conv_ux_perspective.append(("human", user_response))

        # Add the conversation history for both personas
        this_turn = {"researcher": researcher_response, "user": user_response}
        conversation_history.append(this_turn)
    
    return conversation_history
