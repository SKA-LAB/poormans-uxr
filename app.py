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
            <archetype-1>
            Name: [Archetype name]
            Description: [Archetype description]
            </archetype-1>
            ...
            <archetype-7>
            Name: [Archetype name]
            Description: [Archetype description]
            </archetype-7>
            """
            response = call_llm(prompt, st.secrets["api_key"])
        archetypes_data = response.split("<archetype-")
        db = next(get_db()) #re-establish since call_llm closes it.
        for archetype_str in archetypes_data:
            archetype_str = archetype_str.split(">")[1]
            if archetype_str.strip():
                try:
                    name, desc = archetype_str.split("Description:", 1)
                    name = name.replace("Name: ", "").strip()
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
        with st.spinner("Generating specific personas for each archetype... This will take a few moments, please do not navigate away..."):
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
    with st.spinner("Running interviews... This will take a few minutes, feel free to get a coffee but do NOT close this page or you will lose the interviews."):
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
        with st.spinner("Analyzing Interviews... This may take a few minutes, feel free to get a coffee but do NOT close this page or you will lose the analysis."):
            interviews = get_interviews_by_project(db, project_uuid)
            all_conversations = []
            for interview in interviews:
                all_conversations.extend(json.loads(interview.interview_transcript)) 
            clusters = cluster_sentences(all_conversations, st.secrets["api_key"])
            cluster_summaries = summarize_each_cluster(clusters, st.session_state.product_desc, 
                                                    st.session_state.user_group_desc,
                                                    st.secrets["api_key"])
            st.session_state['cluster_summaries'] = cluster_summaries
        for _, summary in cluster_summaries.items():
            with st.expander(f"Theme: {summary["theme"]}"):
                st.write(f"Description: {summary["description"]}")
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
                with st.spinner("Generating comprehensive UXR report... This may take a few minutes."):
                    # Get necessary data
                    personas = get_personas_by_project(db, project_uuid)
                    interviews = get_interviews_by_project(db, project_uuid)
                    cluster_summaries = st.session_state['cluster_summaries']
                    
                    # Generate report content
                    report_content = {}
                    
                    # Executive Summary
                    if include_exec_summary:
                        exec_summary_prompt = f"""
                        Create an executive summary for a UX research report based on the following:
                        
                        Product: {project.product_desc}
                        User Group: {project.user_group_desc}
                        Key Themes: {', '.join([summary['theme'] for _, summary in cluster_summaries.items()])}
                        
                        The executive summary should be concise (150-250 words) and highlight the most important findings
                        and recommendations. Focus on insights that would be most valuable for product development.
                        """
                        report_content['executive_summary'] = call_llm(exec_summary_prompt, st.secrets["api_key"])
                    
                    # Research Background
                    if include_background:
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
                    if include_demographics:
                        demographics_text = "## Participant Demographics\n\n"
                        for i, persona in enumerate(personas, 1):
                            demographics_text += f"### Participant {i}: {persona.persona_name}\n\n"
                            
                            # Extract key demographic information from persona description
                            demo_prompt = f"""
                            Extract and summarize the key demographic information from this persona description in 3-4 sentences:
                            
                            {persona.persona_desc}
                            
                            Focus only on demographics, age, location, and background. Be concise.
                            """
                            demo_summary = call_llm(demo_prompt, st.secrets["api_key"])
                            demographics_text += f"{demo_summary}\n\n"
                        
                        report_content['demographics'] = demographics_text
                    
                    # Key Findings
                    if include_key_findings:
                        findings_prompt = f"""
                        Create a "Key Findings" section for a UX research report based on these themes:
                        
                        {json.dumps([summary for _, summary in cluster_summaries.items()])}
                        
                        For each theme, provide:
                        1. A clear headline that captures the essence of the finding
                        2. A brief explanation (2-3 sentences)
                        3. The potential impact on the product design
                        
                        Format each finding as a separate section with markdown formatting.
                        """
                        report_content['key_findings'] = "## Key Findings\n\n" + call_llm(findings_prompt, st.secrets["api_key"])
                    
                    # Detailed Analysis
                    if include_detailed_analysis:
                        detailed_analysis = "## Detailed Analysis\n\n"
                        for i, (_, summary) in enumerate(cluster_summaries.items(), 1):
                            detailed_analysis += f"### Theme {i}: {summary['theme']}\n\n"
                            detailed_analysis += f"{summary['description']}\n\n"
                            detailed_analysis += "**Supporting Evidence:**\n\n"
                            detailed_analysis += f"{summary['sample_sentences']}\n\n"
                        
                        report_content['detailed_analysis'] = detailed_analysis
                    
                    # Recommendations
                    if include_recommendations:
                        recommendations_prompt = f"""
                        Create a "Recommendations" section for a UX research report based on these research findings:
                        
                        Product: {project.product_desc}
                        User Group: {project.user_group_desc}
                        Key Themes: {json.dumps([summary for _, summary in cluster_summaries.items()])}
                        
                        Provide 5-7 specific, actionable recommendations that:
                        1. Address the key pain points identified
                        2. Leverage the opportunities discovered
                        3. Are realistic to implement
                        
                        Format each recommendation with:
                        - A clear, actionable title
                        - A brief explanation of the recommendation
                        - The expected impact or benefit
                        
                        Use markdown formatting.
                        """
                        report_content['recommendations'] = "## Recommendations\n\n" + call_llm(recommendations_prompt, st.secrets["api_key"])
                    
                    # Appendix
                    if include_appendix:
                        appendix = "## Appendix: Raw Interview Data\n\n"
                        for i, interview in enumerate(interviews, 1):
                            persona = db.query(Persona).filter(Persona.persona_uuid == interview.persona_uuid).first()
                            appendix += f"### Interview {i}: Conversation with {persona.persona_name}\n\n"
                            
                            conversation = json.loads(interview.interview_transcript)
                            for j, turn in enumerate(conversation, 1):
                                appendix += f"**Researcher:** {turn['researcher']}\n\n"
                                appendix += f"**{persona.persona_name}:** {turn['user']}\n\n"
                            
                            appendix += "---\n\n"
                        
                        report_content['appendix'] = appendix
                    
                    # Compile full report
                    full_report = f"# {report_title}\n\n"
                    
                    if include_exec_summary:
                        full_report += "## Executive Summary\n\n"
                        full_report += report_content['executive_summary'] + "\n\n"
                    
                    for section in ['research_background', 'demographics', 'key_findings', 
                                   'detailed_analysis', 'recommendations', 'appendix']:
                        if section in report_content:
                            full_report += report_content[section] + "\n\n"
                    
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