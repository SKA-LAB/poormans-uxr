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
    Persona,
    UXRResearcher,
)
import json
from utils.interview_utils import get_researcher_persona, simulate_interview
from utils.convo_analysis import call_llm, cluster_sentences, summarize_each_cluster
import time
from datetime import datetime

# Initialize the database
init_db()

# --- Session State Management ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.session_state['current_project_uuid'] = None
    st.session_state['interview_queue'] = []  # (persona_uuid, uxr_persona_uuid)
    st.session_state['interview_status'] = {}  # interview_uuid: status

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
                                      st.secrets["api_key"])

    create_interview(db, persona_uuid, uxr_persona_uuid, project_uuid, json.dumps(transcript))
    st.session_state['interview_status'][interview_uuid] = "complete"
    db.close()

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
                st.markdown(f"<div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;'>{turn['researcher']}</div>", unsafe_allow_html=True)
                
                # Display user message with different styling
                st.markdown("**User:**")
                st.markdown(f"<div style='background-color: #e6f3ff; padding: 10px; border-radius: 5px; margin-bottom: 20px;'>{turn['user']}</div>", unsafe_allow_html=True)
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
            st.experimental_rerun()
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
        st.experimental_rerun() #rerun to clear fields.

def create_project_page():
    st.title("Create New Project")
    # Project Name will be generated, but user can change
    user_group_desc = st.text_area("Broad User Group Description", placeholder="Example: University-enrolled engineering students")
    product_desc = st.text_area("General Product Category/Type", placeholder="Example: A mobile app for collaborative note-taking")

    if st.button("Create Project"):
        db = next(get_db())
        with st.spinner("Creating project... Please wait."):
            # LLM generated project name.
            prompt = f"""
            Generate a concise project name based on:
            User group: {user_group_desc}
            Product Type: {product_desc}
            Respond only with the project name. 

            Project name:
            """
            project_name = call_llm(prompt, st.secrets["api_key"])
        project = create_project(db, st.session_state['user_id'], user_group_desc, product_desc, project_name)
        st.session_state['current_project_uuid'] = project.project_uuid
        st.session_state['project_name'] = project.project_name
        st.session_state['user_group_desc'] = user_group_desc #store in session state for later
        st.session_state['product_desc'] = product_desc #store in session state for later
        db.close()
        st.success(f"Project '{project_name}' created!")
        st.experimental_rerun()

def project_main_page(project_uuid):
    db = next(get_db())
    project = get_project_by_uuid(db, project_uuid)

    st.title(f"Project: {project.project_name}")
    #make project name editable
    new_project_name = st.text_input("Edit Project Name", project.project_name)
    if new_project_name != project.project_name:
        project.project_name = new_project_name
        update_project(db, project_uuid, {'project_name':new_project_name})


    st.write(f"**User Group:** {project.user_group_desc}")
    st.write(f"**Product Category:** {project.product_desc}")

    # --- Persona Archetypes ---
    st.header("Persona Archetypes")
    if st.button("Generate Persona Archetypes"):
        with st.spinner("Generating persona archetypes... This might take a few moments."):
            prompt = f"""
            Generate 7 persona archetypes based on:
            User group: {project.user_group_desc}
            Product: {project.product_desc}
            Persona archetypes are not specific personas but categories of user personas that are distinct from each other and can be used as
            building blocks for creating specific personas.

            Format your output as:
            <Archetype Number 1>
            Name: [Archetype name]
            Description: [Archetype description]
            </Archetype Number 1>
            ...
            <Archetype Number 5>
            Name: [Archetype name]
            Description: [Archetype description]
            </Archetype Number 5>
            """
            response = call_llm(prompt, st.secrets["api_key"])
        archetypes_data = response.split("Name:")
        db = next(get_db()) #re-establish since call_llm closes it.
        for archetype_str in archetypes_data:
            if archetype_str.strip():
                try:
                    name, desc = archetype_str.split("Description:", 1)
                    name = name.strip()
                    desc = desc.strip()
                    create_persona_archetype(db, project_uuid, name, desc)
                except ValueError:
                    st.error(f"Error parsing archetype: {archetype_str}")
        db.close()
        st.experimental_rerun()

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
            st.experimental_rerun()


    # --- Specific Personas ---
    st.header("Specific Personas")
    if st.button("Generate Personas"):
        archetypes = get_archetypes_by_project(db, project_uuid)
        with st.spinner("Generating specific personas for each archetype... This might take a few moments."):
            for archetype in archetypes:
                prompt = f"""
                Generate a specific user persona based on this archetype:
                {archetype.persona_archetype_name}: {archetype.persona_archetype_desc}

                Create a clear, complete, and well-structured description of the persona with the following sections:
                - Name: [Name of the persona].
                - Age: [Age of the persona].
                - Demographics: [Demographics of the persona (e.g., gender, race, ethnicity)].
                - Location: [The location of the persona].
                - Motivations: [The motivations of the persona].
                - Goals and needs: [The goals and needs of the persona].
                - Values: [The values and aspirations of the persona].
                - Attitudes and beliefs: [The attitudes and beliefs of the persona].
                - Lifestyle: [The lifestyle of the persona].
                - Daily routine: [The daily routine of the persona].
                - Devise usage: [The usage of technology by the persona].
                - Software familiarity: [Their level of comfort with specific software or platforms]
                - Digital literacy: [Confidence in navigating digital platforms and software]
                - Pain points: [The pain points and concerns of the persona].
                - Delightful moments: [The moments and experiences that bring the persona joy and satisfaction].
                """
                response = call_llm(prompt, st.secrets["api_key"])
                try:
                    name, desc = response.split("Age:", 1)
                    name = name.replace("Name:", "").strip()
                    desc = "Age:" + desc.strip()
                    create_persona(db, project_uuid, archetype.persona_arch_uuid, name, desc)
                except ValueError:
                    st.error(f"Error parsing persona from response: {response}")
        st.experimental_rerun()
    #Display, edit, add personas.
    personas = get_personas_by_project(db, project_uuid)
    for persona in personas:
        with st.expander(persona.persona_name, expanded = True):
            new_name = st.text_input("Name", persona.persona_name, key=f"pname_{persona.persona_uuid}")
            new_desc = st.text_area("Description\n", persona.persona_desc, key=f"pdesc_{persona.persona_uuid}")
            if new_name != persona.persona_name or new_desc != persona.persona_desc:
                update_persona(db, persona.persona_uuid, {'persona_name': new_name, 'persona_desc': new_desc})

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
    if st.button("Run Interviews"):
        personas = get_personas_by_project(db, project_uuid)
        researcher = get_uxr_researcher_by_project(db, project_uuid)
        if researcher:  # Check if researcher exists
            for persona in personas:
                st.session_state['interview_queue'].append((persona.persona_uuid, researcher.uxr_persona_uuid))
        else:
             st.error("Please generate the UXR Researcher Persona first.")
    #Process interviews
    with st.spinner("Running interviews... This might take a few minutes, feel free to get a coffee but do NOT close this page."):
        if st.session_state['interview_queue']:
            persona_uuid, uxr_persona_uuid = st.session_state['interview_queue'].pop(0) #get the oldest one.
            run_interview_simulation(persona_uuid, uxr_persona_uuid, project_uuid) #this also updates the session state.
    #Display interviews
    interviews = get_interviews_by_project(db, project_uuid)
    for interview in interviews:
        persona = db.query(Persona).filter(Persona.persona_uuid == interview.persona_uuid).first()
        status = st.session_state['interview_status'].get(interview.interview_uuid,"Unknown")
        with st.expander(f"Interview with {persona.persona_name} ({status})"):
            display_interview(interview.interview_transcript)

    # --- Analyze Interviews ---
    st.header("Analyze Interviews")
    if st.button("Analyze"):
        with st.spinner("Analyzing Interviews... This may take a few minutes, feel free to get a coffee but do NOT close this page."):
            interviews = get_interviews_by_project(db, project_uuid)
            all_conversations = []
            for interview in interviews:
                all_conversations.extend(json.loads(interview.interview_transcript)) 
            clusters = cluster_sentences(all_conversations, st.secrets["api_key"])
            cluster_summaries = summarize_each_cluster(clusters, st.session_state.product_desc, 
                                                    st.session_state.user_group_desc,
                                                    st.secrets["api_key"])
        for cluster_id, summary in cluster_summaries.items():
            with st.expander(f"Theme {summary["theme"]}"):
                st.write(summary["description"])
    # --- UXR Report ---
    #TODO: Add Report Section.
    db.close()

# --- Main App Logic ---

if not st.session_state['logged_in']:
    choice = st.sidebar.selectbox("Navigation", ["Login", "Create Account"])
    if choice == "Login":
        login_page()
    else:
        signup_page()
else:
    st.sidebar.write(f"Logged in as: {st.session_state['user_id']}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['user_id'] = None
        st.session_state['current_project_uuid'] = None
        st.experimental_rerun()

    if st.session_state['current_project_uuid'] is None:
        create_project_page()
    else:
        project_main_page(st.session_state['current_project_uuid'])