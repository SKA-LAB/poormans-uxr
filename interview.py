from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
import json
import glob
import datetime
from timeit import default_timer as timer
from utils.do_not_commit import lambda_api_key
import sys

# get model name from command line argument
if len(sys.argv) > 1:
    model_name = sys.argv[1]
else:
    model_name = "llama3.1"

# Define the system message for the researcher chat

# Initialize the LangChain chat models for both personas and an observer
if model_name != "llama3.3":
    researcher_chat = ChatOllama(model=model_name, num_ctx=16000)
    user_chat = ChatOllama(model=model_name, num_ctx=16000)
else:
    researcher_chat = ChatOpenAI(model="llama3.3-70b-instruct-fp8",
                                base_url="https://api.lambdalabs.com/v1",
                                temperature=0.7,
                                api_key=lambda_api_key)
    user_chat = ChatOpenAI(model="llama3.3-70b-instruct-fp8",
                            base_url="https://api.lambdalabs.com/v1",
                            temperature=0.7,
                            api_key=lambda_api_key)

# Define the user researcher persona
user_researcher_persona ="""You are Roxy Buttons, an experienced user researcher specializing in identifying user needs
    and understanding user behavior. Your goal is to ask thoughtful, open-ended questions
    that uncover the user's motivations, challenges, and potential value propositions 
    for using a product or service.
    
    You are currently gathering information and conducting interviews for a product focused 
    on providing surgical video recordings and analysis to surgeons through an online platform 
    to help them learn from each other, share with each other, discover insights, and discuss. 
    Your primary goal is to understand the value proposition of this platform and explore the 
    problem space more completely. You are tasked with interviewing surgeons from different surgical specialties, 
    demographics, locations, and healthcare settings.
    
    You are interviewing a surgeon right now."""

# load user personas from files
user_persona_files = glob.glob("personas/*.txt")

# Function to simulate the conversation between the two personas
def simulate_conversation(researcher_chat, user_chat, conv_ux_perspective, conv_user_perspective, turns=5):
    conversation_history = []
    for _ in range(turns):
        # Researcher asks a question
        researcher_response = researcher_chat.invoke(conv_ux_perspective)
        print(f"Researcher: {researcher_response.content}\n")
        conv_ux_perspective.append(("assistant", researcher_response.content))

        # add the researcher output to the user conversation perspective
        conv_user_perspective.append(("human", researcher_response.content))
        
        # User responds to the question
        user_response = user_chat.invoke(conv_user_perspective)
        print(f"User: {user_response.content}\n")
        conv_user_perspective.append(("assistant", user_response.content))

        # add the user output to the researcher conversation perspective
        conv_ux_perspective.append(("human", user_response.content))

        # Add the conversation history for both personas
        this_turn = {"researcher": researcher_response.content, "user": user_response.content}
        conversation_history.append(this_turn)
    
    return conversation_history

# Initialize the conversation for each user persona
for persona_file in user_persona_files:
    tic = timer()
    # Load the user persona
    with open(persona_file, "r") as f:
        user_persona = f.read().strip()
    f.close()
    
    # Initialize system prompts for each persona
    researcher_prompt = ("system", user_researcher_persona)
    user_prompt = ("system", "You are the following person. " + user_persona + ". You are currently being interviewed by a user researcher.")

    # Start the conversation
    conv_ux_perspective = [
        researcher_prompt,
        ("human", "Let's begin the interview."),
    ]

    conv_user_perspective = [
        user_prompt,
    ]

    # Run the simulation
    conversation = simulate_conversation(researcher_chat, user_chat, conv_ux_perspective, conv_user_perspective, turns=5)
    toc = timer()
    print(f"Simulation time for {persona_file}: {toc - tic:.4f} seconds")
    output = {
        "conversation_history": conversation,
        "model_name": model_name,
        "persona_file": persona_file,
        "simulation_time": f"{toc - tic:.4f} seconds"
    }
    
    # Save the conversation history
    current_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    conversation_file = persona_file.replace("personas/", "interviews/").replace(".txt", f"_conversation_{current_datetime}.json")
    with open(conversation_file, "w") as f:
        json.dump(output, f, indent=4)
    f.close()
