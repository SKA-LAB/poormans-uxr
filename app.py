"""
Remember to create .streamlit folder with secrets.toml file with an api_key value

To support pdf conversion, wkhtmltopdf needs to be installed on the system:
For Ubuntu/Debian: sudo apt-get install wkhtmltopdf
For macOS: brew install wkhtmltopdf
"""

import streamlit as st
from uxr_app.database import (
    init_db,
    get_db,
    create_user,
    get_user_by_email,
    create_project,
    get_project_by_uuid,
    create_persona_archetype,
    get_archetypes_by_project,
    create_persona,
    get_personas_by_project,
    create_uxr_researcher,
    get_uxr_researcher_by_project,
    create_interview,
    get_interviews_by_project,
    update_project,
    update_persona,
    update_persona_archetype,
    update_uxr_researcher,
    get_existing_persona_names,
    Persona,
    UXRResearcher,
    Project,
    Interview,
    PersonaArchetype,
)
from utils.prompt_templates import (
    get_project_name_prompt,
    get_persona_archetypes_prompt,
    get_specific_persona_prompt,
    parse_persona_response,
    get_exec_summary_prompt,
    get_recommendations_prompt,
    get_findings_prompt,
    get_demographics_prompt
)
from uxr_app.auth import (logout_user)
import json
from utils.interview_utils import get_researcher_persona, simulate_interview
from utils.convo_analysis import call_llm, cluster_sentences, summarize_each_cluster
import time
from datetime import datetime
import uuid
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import torch
import logging

torch.classes.__path__ = []  # to support sentence-transformers

# Set up logging with script name, line number, and timestamp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)
logger.info("Application started")

model_key = "model_name"

def initialize_session_state():
    """Initialize all session state variables if they don't exist."""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_id'] = None
        st.session_state['current_project_uuid'] = None
        st.session_state['guest_mode'] = False
        st.session_state['guest_user_id'] = None
        st.session_state['guest_projects'] = []

def reset_session_state():
    """Reset all session state variables on logout."""
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.session_state['current_project_uuid'] = None
    st.session_state['guest_mode'] = False
    st.session_state['guest_user_id'] = None
    
    # Clear analysis-related state
    if 'interview_status' in st.session_state:
        del st.session_state['interview_status']
    if 'cluster_summaries' in st.session_state:
        del st.session_state['cluster_summaries']
    if 'uxr_report' in st.session_state:
        del st.session_state['uxr_report']

# Set page configuration to wide mode
st.set_page_config(layout="wide")

# Initialize the database
init_db()

# --- Session State Management ---
initialize_session_state()

# Add a function to handle guest user creation
def create_guest_user():
    """Create a temporary guest user and return the user_id"""
    db = next(get_db())
    guest_email = f"guest_{uuid.uuid4().hex[:8]}@temp.uxr"
    temp_password = uuid.uuid4().hex
    user = create_user(db, guest_email, temp_password)
    db.close()
    return user.user_id, guest_email, temp_password

# --- Helper function for simulating interviews ---
def run_interview_simulation(persona_uuid, uxr_persona_uuid, project_uuid):
    """Simulates running an interview and updates the database."""
    db = next(get_db())
    interview_uuid = f"interview-{persona_uuid}-{uxr_persona_uuid}-{time.time()}"
    st.session_state['interview_status'][interview_uuid] = "in-progress"
    persona = db.query(Persona).filter(Persona.persona_uuid == persona_uuid).first()
    uxr_persona = db.query(UXRResearcher).filter(UXRResearcher.uxr_persona_uuid == uxr_persona_uuid).first()

    transcript = simulate_interview(uxr_persona.uxr_persona_name, uxr_persona.uxr_persona_desc, 
                                      persona.persona_name, persona.persona_desc, 
                                      st.session_state.product_desc,
                                      st.secrets["api_key"],
                                      model_name=st.secrets[model_key])

    create_interview(db, persona_uuid, uxr_persona_uuid, project_uuid, json.dumps(transcript))
    st.session_state['interview_status'][interview_uuid] = "complete"
    db.close()

def run_interview_in_background(persona_uuid, uxr_persona_uuid, project_uuid):
    """Runs an interview simulation in a background thread and updates the database directly."""
    try:
        # Set up thread-specific logging
        thread_id = threading.current_thread().name
        logging.info(f"[{thread_id}] Starting interview for persona UUID: {persona_uuid}")
        
        # Create a new database session for this thread
        from sqlalchemy.orm import sessionmaker
        from uxr_app.database import engine
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        try:
            # Get the necessary data
            persona = db.query(Persona).filter(Persona.persona_uuid == persona_uuid).first()
            uxr_persona = db.query(UXRResearcher).filter(UXRResearcher.uxr_persona_uuid == uxr_persona_uuid).first()
            project = db.query(Project).filter(Project.project_uuid == project_uuid).first()
            
            if not persona or not uxr_persona or not project:
                logging.error(f"[{thread_id}] Could not find required data: persona={bool(persona)}, uxr_persona={bool(uxr_persona)}, project={bool(project)}")
                return
            
            logging.info(f"[{thread_id}] Retrieved data for persona: {persona.persona_name}")
            
            # Run the interview simulation
            logging.info(f"[{thread_id}] Starting interview simulation for persona: {persona.persona_name}")
            
            # Import secrets directly in this thread
            import json
            from utils.interview_utils import simulate_interview
            
            # Get API key and model name from secrets.toml
            import toml
            import os
            
            # Determine the path to secrets.toml
            secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
            
            try:
                with open(secrets_path, 'r') as f:
                    secrets = toml.load(f)
                    api_key = secrets.get("api_key")
                    model_name = secrets.get("model_name")
                    
                    if not api_key:
                        logging.error(f"[{thread_id}] API key not found in secrets.toml")
                        return
                        
                    logging.info(f"[{thread_id}] Successfully loaded API key and model name")
                    
                    # Run the interview simulation
                    transcript = simulate_interview(
                        uxr_persona.uxr_persona_name, 
                        uxr_persona.uxr_persona_desc, 
                        persona.persona_name, 
                        persona.persona_desc, 
                        project.product_desc,
                        api_key,
                        model_name=model_name
                    )
                    
                    logging.info(f"[{thread_id}] Interview simulation completed for persona: {persona.persona_name}")
                    
                    # Check if an interview already exists
                    existing_interview = db.query(Interview).filter(
                        Interview.persona_uuid == persona_uuid,
                        Interview.uxr_persona_uuid == uxr_persona_uuid,
                        Interview.project_uuid == project_uuid
                    ).first()
                    
                    if existing_interview:
                        logging.info(f"[{thread_id}] Interview already exists for persona {persona.persona_name}, skipping save")
                    else:
                        # Save the interview to the database
                        logging.info(f"[{thread_id}] Saving interview to database for persona: {persona.persona_name}")
                        
                        # Create interview with transcript
                        interview_uuid = f"{persona_uuid}-{uxr_persona_uuid}-{project_uuid}"
                        new_interview = Interview(
                            persona_uuid=persona_uuid,
                            uxr_persona_uuid=uxr_persona_uuid,
                            project_uuid=project_uuid,
                            interview_transcript=json.dumps(transcript),
                            interview_uuid=interview_uuid
                        )
                        
                        db.add(new_interview)
                        db.commit()
                        logging.info(f"[{thread_id}] Successfully saved interview for persona: {persona.persona_name}")
                    
            except Exception as e:
                logging.error(f"[{thread_id}] Error loading secrets or running interview: {str(e)}")
                raise
                
        finally:
            # Close the database session
            db.close()
            logging.info(f"[{thread_id}] Database session closed")
            
    except Exception as e:
        logging.error(f"[{thread_id}] Unhandled error in interview thread: {str(e)}", exc_info=True)

# --- Helper function for displaying interviews ---
def display_interview(interview_transcript: str):
    try:
        # Parse the JSON string into a Python object
        conversation = json.loads(interview_transcript)
        
        # Create a container for the conversation
        conversation_container = st.container()
        
        with conversation_container:
            for turn in conversation:
                # Display researcher message with styling
                st.markdown("**Researcher:**")
                st.markdown(f"<div style='background-color: #2e3440; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #88c0d0; color: #d8dee9;'>{turn['researcher']}</div>", unsafe_allow_html=True)
                
                # Display user message with different styling
                st.markdown("**User:**")
                st.markdown(f"<div style='background-color: #3b4252; padding: 15px; border-radius: 8px; margin-bottom: 25px; border-left: 4px solid #a3be8c; color: #e5e9f0;'>{turn['user']}</div>", unsafe_allow_html=True)
    except json.JSONDecodeError:
        # Fallback to original display if JSON parsing fails
        st.write("Could not parse conversation format. Displaying raw transcript:")
        st.write(interview_transcript)

# --- UI Components ---

def login_page():
    st.title("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        db = next(get_db())
        user = get_user_by_email(db, email)
        db.close()
        if user and user.password == password:  # In real app, compare hashed passwords
            st.session_state['logged_in'] = True
            st.session_state['user_id'] = user.user_id
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid credentials.")

def signup_page():
    st.title("Create Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    if st.button("Create Account"):
        if password != confirm_password:
            st.error("Passwords do not match.")
            return
        db = next(get_db())
        if get_user_by_email(db, email):
            st.error("Email already exists.")
            db.close()
            return

        create_user(db, email, password)  # Hash the password!
        db.close()
        st.success("Account created successfully! Please log in.")
        st.rerun() #rerun to clear fields.

def create_project_page():
    st.title("Create New Project")

    # Check user's project count
    db = next(get_db())
    # Get all projects for the user, ordered by creation date
    user_projects = db.query(Project).filter(Project.user_id == st.session_state['user_id']).order_by(Project.creation_date).all()
    project_count = len(user_projects)
    db.close()
    
    # Display warning if at project limit
    if project_count >= 5:
        st.warning(f"You currently have {project_count} projects. Creating a new project will delete your oldest project.")
        if not st.checkbox("I understand and want to continue"):
            st.info("Please delete an existing project or check the box above to continue.")
            return
        
        # If user agrees to continue, prepare to delete oldest project
        oldest_project = user_projects[0]
        st.warning(f"Creating a new project will delete: '{oldest_project.project_name}'")
    
    # Project Name will be generated, but user can change
    user_group_desc = st.text_area("Broad User Group Description", placeholder="Example: University-enrolled engineering students")
    product_desc = st.text_area("General Product Category/Type", placeholder="Example: A mobile app for collaborative note-taking")

    if st.button("Create Project"):
        db = next(get_db())

        # Delete oldest project if at the limit
        if project_count >= 5:
            oldest_project_id = user_projects[0].project_uuid
            
            # Delete associated records first (cascade delete isn't automatic)
            # Delete interviews
            interviews = db.query(Interview).filter(Interview.project_uuid == oldest_project_id).all()
            for interview in interviews:
                db.delete(interview)
            
            # Delete personas
            personas = db.query(Persona).filter(Persona.project_uuid == oldest_project_id).all()
            for persona in personas:
                db.delete(persona)
                
            # Delete UX researchers
            researchers = db.query(UXRResearcher).filter(UXRResearcher.project_uuid == oldest_project_id).all()
            for researcher in researchers:
                db.delete(researcher)
                
            # Delete persona archetypes
            archetypes = db.query(PersonaArchetype).filter(PersonaArchetype.project_uuid == oldest_project_id).all()
            for archetype in archetypes:
                db.delete(archetype)
            
            # Delete the project itself
            db.delete(oldest_project)
            
            db.commit()
            st.success(f"Project '{oldest_project.project_name}' has been deleted to make room for your new project.")

        with st.spinner("Creating project... Please wait."):
            # LLM generated project name.
            prompt = get_project_name_prompt(user_group_desc, product_desc)
            project_name = call_llm(prompt, st.secrets["api_key"], st.secrets[model_key])
        project = create_project(db, st.session_state['user_id'], user_group_desc, product_desc, project_name)
        st.session_state['current_project_uuid'] = project.project_uuid
        st.session_state['project_name'] = project.project_name
        st.session_state['user_group_desc'] = user_group_desc #store in session state for later
        st.session_state['product_desc'] = product_desc #store in session state for later
        
        # Add project to guest projects list if in guest mode
        if st.session_state.get('guest_mode', False):
            if 'guest_projects' not in st.session_state:
                st.session_state['guest_projects'] = []
            st.session_state['guest_projects'].append(project.project_uuid)

        db.close()
        st.success(f"Project '{project_name}' created!")
        st.rerun()

def generate_uxr_report(project, personas, interviews, cluster_summaries, report_options, api_key, model_name):
    """
    Generate a UX research report based on the provided data and selected sections.
    
    Args:
        project: The project object containing project details
        personas: List of persona objects
        interviews: List of interview objects
        cluster_summaries: Dictionary of cluster summaries
        report_options: Dictionary with boolean flags for which sections to include and report title
        api_key: API key for LLM calls
        
    Returns:
        dict: The generated report content by section
        str: The compiled full report
    """
    report_content = {}
    
    # Executive Summary
    if report_options.get('include_exec_summary', False):
        themes = [summary['theme'] for _, summary in cluster_summaries.items()]
        exec_summary_prompt = get_exec_summary_prompt(project.product_desc, 
                                                    project.user_group_desc,
                                                    themes)
        report_content['executive_summary'] = call_llm(exec_summary_prompt, api_key, model_name)
    
    # Research Background
    if report_options.get('include_background', False):
        report_content['research_background'] = f"""
        ## Research Background
        
        **Project:** {project.project_name}
        
        **Product Description:** {project.product_desc}
        
        **Target User Group:** {project.user_group_desc}
        
        **Research Methodology:** This research was conducted using simulated interviews with AI-generated personas 
        representing the target user group. The interviews were designed to explore user needs, pain points, 
        and potential value propositions related to the product. Since personas were AI-generated, there may be 
        biases and caveats to the research. Please use these results as directional guidance for product development
        and validate all findings with customer interviews and product stakeholders.
        
        **Research Period:** {datetime.now().strftime("%B %Y")}
        """
    
    # Participant Demographics
    if report_options.get('include_demographics', False):
        demographics_text = "## Participant Demographics\n\n"
        for i, persona in enumerate(personas, 1):
            demographics_text += f"### Participant {i}: {persona.persona_name}\n\n"
            
            # Extract key demographic information from persona description
            demo_prompt = get_demographics_prompt(persona.persona_desc)
            demo_summary = call_llm(demo_prompt, api_key, model_name)
            demographics_text += f"{demo_summary}\n\n"
        
        report_content['demographics'] = demographics_text
    
    # Key Findings
    if report_options.get('include_key_findings', False):
        findings_prompt = get_findings_prompt(json.dumps([summary for _, summary in cluster_summaries.items()]))
        report_content['key_findings'] = "## Key Findings\n\n" + call_llm(findings_prompt, api_key, model_name)
    
    # Detailed Analysis
    if report_options.get('include_detailed_analysis', False):
        detailed_analysis = "## Detailed Analysis\n\n"
        for i, (_, summary) in enumerate(cluster_summaries.items(), 1):
            detailed_analysis += f"### Theme {i}: {summary['theme']}\n\n"
            detailed_analysis += f"{summary['description']}\n\n"
            detailed_analysis += "**Supporting Evidence:**\n\n"
            detailed_analysis += f"{summary['sample_sentences']}\n\n"
        
        report_content['detailed_analysis'] = detailed_analysis
    
    # Recommendations
    if report_options.get('include_recommendations', False):
        recommendations_prompt = get_recommendations_prompt(
            project.product_desc,
            project.user_group_desc,
            json.dumps([summary for _, summary in cluster_summaries.items()])
        )
        report_content['recommendations'] = "## Recommendations\n\n" + call_llm(recommendations_prompt, api_key, model_name)
    
    # Appendix
    if report_options.get('include_appendix', False):
        appendix = "## Appendix: Raw Interview Data\n\n"
        for i, interview in enumerate(interviews, 1):
            persona = next((p for p in personas if p.persona_uuid == interview.persona_uuid), None)
            if persona:
                appendix += f"### Interview {i}: Conversation with {persona.persona_name}\n\n"
                
                conversation = json.loads(interview.interview_transcript)
                for j, turn in enumerate(conversation, 1):
                    appendix += f"**Researcher:** {turn['researcher']}\n\n"
                    appendix += f"**{persona.persona_name}:** {turn['user']}\n\n"
                
                appendix += "---\n\n"
        
        report_content['appendix'] = appendix
    
    # Compile full report
    full_report = f"# {report_options.get('report_title', 'UXR Report')}\n\n"
    
    if report_options.get('include_exec_summary', False):
        full_report += "## Executive Summary\n\n"
        full_report += report_content['executive_summary'] + "\n\n"
    
    for section in ['research_background', 'demographics', 'key_findings', 
                'detailed_analysis', 'recommendations', 'appendix']:
        if section in report_content:
            full_report += report_content[section] + "\n\n"
    
    return report_content, full_report

def project_main_page(project_uuid):
    db = next(get_db())
    project = get_project_by_uuid(db, project_uuid)

    st.title(f"Project: {project.project_name}")
    #make project name editable
    new_project_name = st.text_input("Edit Project Name", project.project_name)
    if new_project_name != project.project_name:
        project.project_name = new_project_name
        update_project(db, project_uuid, {'project_name':new_project_name})
        st.rerun()


    st.write(f"**User Group:** {project.user_group_desc}")
    st.write(f"**Product Category:** {project.product_desc}")

    # --- Persona Archetypes ---
    st.header("Persona Archetypes")
    if st.button("Generate Persona Archetypes"):
        st.write("Create persona archetypes based on user group and product description.")
        with st.spinner("Generating persona archetypes... This might take a few moments."):
            prompt = get_persona_archetypes_prompt(project.user_group_desc, project.product_desc)
            response = call_llm(prompt, st.secrets["api_key"], st.secrets[model_key])
        archetypes_data = response.split("<archetype-")
        db = next(get_db()) #re-establish since call_llm closes it.
        for archetype_str in archetypes_data:
            if len(archetype_str) > 5:
                archetype_str = archetype_str.split(">")[1]
                archetype_str = archetype_str.split("</archetype-")[0]
                if archetype_str.strip():
                    try:
                        name, desc = archetype_str.split("Description:", 1)
                        name = name.replace("Name: ", "").strip()
                        desc = desc.strip()
                        create_persona_archetype(db, project_uuid, name, desc)
                    except ValueError:
                        st.error(f"Error parsing archetype: {archetype_str}")
        db.close()
        st.rerun()

    #display, edit, add archetypes.
    db = next(get_db()) #re-establish since call_llm closes it.
    archetypes = get_archetypes_by_project(db, project_uuid)
    for archetype in archetypes:
        with st.expander(archetype.persona_archetype_name, expanded=True):
            new_name = st.text_input("Name", archetype.persona_archetype_name, key=f"name_{archetype.persona_arch_uuid}")
            new_desc = st.text_area("Description", archetype.persona_archetype_desc, key=f"desc_{archetype.persona_arch_uuid}")
            if new_name != archetype.persona_archetype_name or new_desc != archetype.persona_archetype_desc:
                update_persona_archetype(db, archetype.persona_arch_uuid, {'persona_archetype_name': new_name, 'persona_archetype_desc': new_desc})

    #allow adding new
    with st.expander("Add New Archetype"):
        new_arch_name = st.text_input("Archetype Name")
        new_arch_desc = st.text_area("Archetype Description")
        if st.button("Add Archetype", key = "add_new_archetype"):
            create_persona_archetype(db, project_uuid, new_arch_name, new_arch_desc)
            st.rerun()


    # --- Specific Personas ---
    st.header("Specific Personas")
    if st.button("Generate Personas"):
        st.write("Create specific personas based on archetypes.")
        archetypes = get_archetypes_by_project(db, project_uuid)
        existing_names = get_existing_persona_names(db, project_uuid)
        with st.spinner("Generating specific personas for each archetype... This will take a few moments, please do not navigate away..."):
            for archetype in archetypes:
                prompt = get_specific_persona_prompt(archetype.persona_archetype_name, 
                                                     archetype.persona_archetype_desc,
                                                     existing_names,
                                                     project.product_desc)
                response = call_llm(prompt, st.secrets["api_key"], st.secrets[model_key])
                try:
                    persona_dict = parse_persona_response(response)
                    name = str(persona_dict['name'])
                    desc = str(persona_dict['description'])
                    create_persona(db, project_uuid, archetype.persona_arch_uuid, name, desc)
                    existing_names.append(name)
                except ValueError:
                    st.error(f"Error parsing persona from response: {response}")
        st.rerun()
    #Display, edit, add personas.
    personas = get_personas_by_project(db, project_uuid)
    for persona in personas:
        archetype = db.query(PersonaArchetype).filter(PersonaArchetype.persona_arch_uuid == persona.persona_arch_uuids).first()
        with st.expander(f"{persona.persona_name} (Archetype: {archetype.persona_archetype_name})", expanded=True):
            new_name = st.text_input("Name", persona.persona_name, key=f"pname_{persona.persona_uuid}")
            new_desc = st.text_area("Description\n", persona.persona_desc, key=f"pdesc_{persona.persona_uuid}")
            st.info(f"Associated Archetype: {archetype.persona_archetype_name}")
            st.text(archetype.persona_archetype_desc)
            if new_name != persona.persona_name or new_desc != persona.persona_desc:
                update_persona(db, persona.persona_uuid, {'persona_name': new_name, 'persona_desc': new_desc})

    # Add new persona manually
    with st.expander("Add New Persona"):
        new_persona_name = st.text_input("New Persona Name")
        new_persona_desc = st.text_area("New Persona Description")
        archetype_options = {arch.persona_archetype_name: arch.persona_arch_uuid for arch in get_archetypes_by_project(db, project_uuid)}
        selected_archetype = st.selectbox("Select Associated Archetype", list(archetype_options.keys()))
        if st.button("Add Persona"):
            if new_persona_name and new_persona_desc and selected_archetype:
                create_persona(db, project_uuid, archetype_options[selected_archetype], new_persona_name, new_persona_desc)
                st.success(f"New persona '{new_persona_name}' added successfully!")
                st.rerun()
            else:
                st.error("Please fill in all fields to add a new persona.")

    
    # --- UXR Researcher Persona ---
    st.header("UX Researcher Persona")
    name, desc = get_researcher_persona()
    create_uxr_researcher(db, project_uuid, name, desc)

    researcher = get_uxr_researcher_by_project(db, project_uuid)
    if researcher:
        with st.expander(researcher.uxr_persona_name, expanded=True):
          new_name = st.text_input("Name", researcher.uxr_persona_name, key=f"rname_{researcher.uxr_persona_uuid}")
          new_desc = st.text_area("Description", researcher.uxr_persona_desc, key=f"rdesc_{researcher.uxr_persona_uuid}")
          if new_name != researcher.uxr_persona_name or new_desc != researcher.uxr_persona_desc:
              update_uxr_researcher(db, researcher.uxr_persona_uuid, {'uxr_persona_name': new_name, 'uxr_persona_desc': new_desc})

    # --- Simulate Interviews ---
    st.header("Simulate Interviews")

    personas = get_personas_by_project(db, project_uuid)
    researcher = get_uxr_researcher_by_project(db, project_uuid)

    if not researcher:
        st.error("Please generate the UXR Researcher Persona first.")
    elif not personas:
        st.error("Please generate Specific Personas first.")
    else:
        # Instead of relying on session state for interview status,
        # check the database directly for each persona
        for persona in personas:
            # Check if interview exists in database
            interview = db.query(Interview).filter(
                Interview.persona_uuid == persona.persona_uuid,
                Interview.uxr_persona_uuid == researcher.uxr_persona_uuid,
                Interview.project_uuid == project_uuid
            ).first()

            col1, col2 = st.columns([3, 1])
            
            with col1:
                if interview:
                    st.info(f"Interview with {persona.persona_name} (Completed)")
                else:
                    st.text(f"Interview with {persona.persona_name} not started")

            with col2:
                button_key = f"interview_button_{persona.persona_uuid}"
                if interview:
                    if st.button("View", key=button_key):
                        st.session_state['selected_interview'] = interview.interview_uuid
                        st.rerun()
                else:
                    if st.button("Run", key=button_key):
                        # Start interview in background thread
                        thread = threading.Thread(
                            target=run_interview_in_background,
                            args=(persona.persona_uuid, researcher.uxr_persona_uuid, project_uuid)
                        )
                        thread.daemon = True
                        thread.start()
                        st.info(f"Interview with {persona.persona_name} started in background. Refresh the page in a minute to see results.")
                        st.rerun()

                # Run all interviews button
        if st.button("Run All Remaining Interviews"):
            remaining_personas = [p for p in personas if not db.query(Interview).filter(
                Interview.persona_uuid == p.persona_uuid,
                Interview.uxr_persona_uuid == researcher.uxr_persona_uuid,
                Interview.project_uuid == project_uuid
            ).first()]
            
            if not remaining_personas:
                st.info("All interviews have already been completed.")
            else:
                # Log the start of batch interview process
                logging.info(f"Starting batch interview process for {len(remaining_personas)} personas")
                st.info(f"Starting interviews for {len(remaining_personas)} personas. This will run in the background. Please do not close this page.")
                
                # Create a thread pool to run interviews concurrently
                max_workers = min(3, len(remaining_personas))  # Don't create more threads than needed
                logging.info(f"Creating ThreadPoolExecutor with max_workers={max_workers}")
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for persona in remaining_personas:
                        logging.info(f"Submitting interview task for persona: {persona.persona_name} (UUID: {persona.persona_uuid})")
                        future = executor.submit(
                            run_interview_in_background,
                            persona.persona_uuid,
                            researcher.uxr_persona_uuid,
                            project_uuid
                        )
                        futures.append(future)
                    
                    logging.info(f"All {len(futures)} interview tasks have been submitted to the executor")
                
                logging.info("ThreadPoolExecutor has completed all tasks")
                st.success("All interviews have been processed. Refresh the page to see results.")
                time.sleep(2)  # Give a moment for the user to see the message
                st.rerun()

        # Display interviews
        if 'selected_interview' in st.session_state:
            interview = db.query(Interview).filter(Interview.interview_uuid == st.session_state['selected_interview']).first()
            if interview:
                persona = db.query(Persona).filter(Persona.persona_uuid == interview.persona_uuid).first()
                with st.expander(f"Interview with {persona.persona_name}", expanded=True):
                    display_interview(interview.interview_transcript)

    # --- Analyze Interviews ---
    st.header("Analyze Interviews")
    if st.button("Analyze"):
        with st.spinner("Analyzing Interviews... This may take a few minutes, feel free to get a coffee but do NOT close this page or you will lose the analysis."):
            interviews = get_interviews_by_project(db, project_uuid)
            all_conversations = []
            for interview in interviews:
                all_conversations.extend(json.loads(interview.interview_transcript)) 
            clusters = cluster_sentences(all_conversations, st.secrets["api_key"], use_local=True)
            cluster_summaries = summarize_each_cluster(clusters, st.session_state.product_desc, 
                                                    st.session_state.user_group_desc,
                                                    st.secrets["api_key"],
                                                    st.secrets[model_key])
            st.session_state['cluster_summaries'] = cluster_summaries
        for _, summary in cluster_summaries.items():
            with st.expander(f"Theme: {summary['theme']}"):
                st.write(f"Description: {summary['description']}")
                st.write(f"Sample sentences:\n{summary['sample_sentences']}")
    
    # --- UXR Report ---
    st.header("UXR Report")
    
    if 'cluster_summaries' in st.session_state:
        report_tab1, report_tab2 = st.tabs(["Generate Report", "Download Report"])
        
        with report_tab1:
            st.subheader("Generate UXR Report")
            report_title = st.text_input("Report Title", f"UXR Report: {project.project_name}")
            
            # Report sections configuration
            include_exec_summary = st.checkbox("Include Executive Summary", value=True)
            include_background = st.checkbox("Include Research Background", value=True)
            include_demographics = st.checkbox("Include Participant Demographics", value=True)
            include_key_findings = st.checkbox("Include Key Findings", value=True)
            include_detailed_analysis = st.checkbox("Include Detailed Analysis", value=True)
            include_recommendations = st.checkbox("Include Recommendations", value=True)
            include_appendix = st.checkbox("Include Appendix (Raw Interview Data)", value=False)
            
            if st.button("Generate Report"):
                # Check if user is in guest mode
                if st.session_state.get('guest_mode', False):
                    st.session_state['show_auth_modal'] = True
                    st.warning("Please log in or create an account to generate and download reports.")
                else:
                    with st.spinner("Generating comprehensive UXR report... This may take a few minutes."):
                        # Get necessary data
                        personas = get_personas_by_project(db, project_uuid)
                        interviews = get_interviews_by_project(db, project_uuid)
                        cluster_summaries = st.session_state['cluster_summaries']
                        
                        # Configure report options
                        report_options = {
                            'report_title': report_title,
                            'include_exec_summary': include_exec_summary,
                            'include_background': include_background,
                            'include_demographics': include_demographics,
                            'include_key_findings': include_key_findings,
                            'include_detailed_analysis': include_detailed_analysis,
                            'include_recommendations': include_recommendations,
                            'include_appendix': include_appendix
                        }
                        
                        # Generate the report
                        _, full_report = generate_uxr_report(
                            project, 
                            personas, 
                            interviews, 
                            cluster_summaries, 
                            report_options, 
                            st.secrets["api_key"],
                            st.secrets[model_key]
                        )
                        
                        # Store the report in session state
                        st.session_state['uxr_report'] = full_report
                    
                # Display the generated report
                st.markdown("### Report Preview")
                st.markdown(st.session_state['uxr_report'])
        
        with report_tab2:
            if 'uxr_report' in st.session_state:
                st.subheader("Download Report")
                
                # Generate PDF
                try:
                    import pdfkit
                    from jinja2 import Template
                    import tempfile
                    import base64
                    
                    # Create HTML from markdown
                    import markdown
                    html_content = markdown.markdown(st.session_state['uxr_report'])
                    
                    # Apply basic styling
                    html_template = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <title>{{ title }}</title>
                        <style>
                            body { font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }
                            h1 { color: #333366; border-bottom: 1px solid #cccccc; padding-bottom: 10px; }
                            h2 { color: #333366; margin-top: 30px; border-bottom: 1px solid #eeeeee; padding-bottom: 5px; }
                            h3 { color: #444444; }
                            blockquote { background-color: #f9f9f9; border-left: 4px solid #cccccc; padding: 10px; margin: 20px 0; }
                            table { border-collapse: collapse; width: 100%; }
                            th, td { border: 1px solid #dddddd; padding: 8px; text-align: left; }
                            th { background-color: #f2f2f2; }
                            .footer { margin-top: 50px; text-align: center; color: #666666; font-size: 0.8em; }
                        </style>
                    </head>
                    <body>
                        {{ content }}
                        <div class="footer">
                            Generated on {{ date }} with PoorMan's UXR
                        </div>
                    </body>
                    </html>
                    """
                    
                    template = Template(html_template)
                    html = template.render(
                        title=report_title,
                        content=html_content,
                        date=datetime.now().strftime("%B %d, %Y")
                    )
                    
                    # Create PDF
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                        pdf_path = f.name
                    
                    # Configure PDF options
                    options = {
                        'page-size': 'A4',
                        'margin-top': '20mm',
                        'margin-right': '20mm',
                        'margin-bottom': '20mm',
                        'margin-left': '20mm',
                        'encoding': "UTF-8",
                        'no-outline': None
                    }
                    
                    # Generate PDF
                    pdfkit.from_string(html, pdf_path, options=options)
                    
                    # Create download button
                    with open(pdf_path, "rb") as pdf_file:
                        pdf_bytes = pdf_file.read()
                    
                    st.download_button(
                        label="Download Report as PDF",
                        data=pdf_bytes,
                        file_name=f"{project.project_name}_UXR_Report.pdf",
                        mime="application/pdf"
                    )
                    
                    # Clean up temporary file
                    import os
                    os.unlink(pdf_path)
                    
                except ImportError:
                    st.warning("PDF generation requires additional packages. Please install pdfkit and jinja2.")
                    
                # Also provide markdown download option as fallback
                st.download_button(
                    label="Download Report as Markdown",
                    data=st.session_state['uxr_report'],
                    file_name=f"{project.project_name}_UXR_Report.md",
                    mime="text/markdown"
                )
            else:
                st.info("Please generate a report first.")
    else:
        st.info("Please analyze interviews first to generate a report.")
    
    db.close()

# --- Main App Logic ---

if not st.session_state['logged_in'] and not st.session_state['guest_mode']:
    choice = st.sidebar.selectbox("Navigation", ["Login", "Create Account", "Continue as Guest"])
    if choice == "Login":
        login_page()
    elif choice == "Create Account":
        signup_page()
    else: # Continue as Guest
        st.session_state['guest_mode'] = True
        st.session_state['guest_user_id'], guest_email, guest_password = create_guest_user()
        st.session_state['user_id'] = st.session_state['guest_user_id']
        st.session_state['guest_email'] = guest_email
        st.session_state['guest_password'] = guest_password
        st.rerun()
else:
    if st.session_state['guest_mode']:
        st.sidebar.write("📝 Guest Mode")
        st.sidebar.info("To save your work, please create an account before leaving")
        if st.sidebar.button("Log in / Create Account"):
            st.session_state['show_auth_modal'] = True
    else:
        st.sidebar.write(f"Logged in as: {st.session_state['user_id']}")

    if st.sidebar.button("Logout"):
        logout_user()
        reset_session_state()
        st.rerun()

    if st.session_state['current_project_uuid'] is None:
        create_project_page()
    else:
        project_main_page(st.session_state['current_project_uuid'])

# Add authentication modal for guest users when needed
if st.session_state.get('show_auth_modal', False):
    with st.sidebar.expander("Authentication Required", expanded=True):
        auth_tab1, auth_tab2 = st.tabs(["Login", "Create Account"])
        
        with auth_tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", key="login_button"):
                db = next(get_db())
                user = get_user_by_email(db, email)
                db.close()
                if user and user.password == password:
                    # Transfer guest data to logged in user
                    if st.session_state['guest_user_id']:
                        db = next(get_db())
                        # Update projects to belong to the logged in user
                        for project_uuid in st.session_state.get('guest_projects', []):
                            project = get_project_by_uuid(db, project_uuid)
                            if project:
                                update_project(db, project_uuid, {'user_id': new_user.user_id})
                        db.close()
                    
                    st.session_state['logged_in'] = True
                    st.session_state['guest_mode'] = False
                    st.session_state['user_id'] = user.user_id
                    st.session_state['show_auth_modal'] = False
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        
        with auth_tab2:
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
            if st.button("Create Account", key="signup_button"):
                error_occurred = False
                if password != confirm_password:
                    st.error("Passwords do not match.")
                    error_occurred = True
                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.error("Please enter a valid email address.")
                    error_occurred = True
                
                if not error_occurred:
                    db = next(get_db())
                    if get_user_by_email(db, email):
                        st.error("Email already exists.")
                        db.close()
                    else:
                        new_user = create_user(db, email, password)
                        
                        # Transfer guest data to new user
                        if st.session_state['guest_user_id']:
                            # Update projects to belong to the new user
                            for project_uuid in st.session_state.get('guest_projects', []):
                                project = get_project_by_uuid(db, project_uuid)
                                if project:
                                    project.user_id = new_user.user_id
                                    db.commit()
                        db.close()
                        
                        st.session_state['logged_in'] = True
                        st.session_state['guest_mode'] = False
                        st.session_state['user_id'] = new_user.user_id
                        st.session_state['show_auth_modal'] = False
                        st.success("Account created successfully! Your work has been transferred to your new account.")
                        st.rerun()