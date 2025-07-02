# poormans-uxr
A cost-effective tool for conducting early and exploratory user research using LLM-based personas.

## Overview
Poor Man's UXR is a Streamlit application that enables product teams to conduct preliminary user research without the high costs and commitment typically associated with recruiting real participants. The tool leverages language models to generate realistic user personas and simulate interviews, providing valuable insights for early-stage product development.

## Features
- **Persona Generation:** Automatically create diverse user archetypes and specific personas based on your target user group and product description
- **Simulated Interviews:** Conduct AI-powered interviews with generated personas to gather insights
- **Conversation Analysis:** Analyze interview transcripts to identify key themes and patterns
- **UX Research Reports:** Generate comprehensive research reports with executive summaries, key findings, and recommendations
- **User Authentication:** Login system to save and manage your research projects

## Getting Started

### Prerequisites
- Python 3.10+
- pip package manager
- access to OpenAI API endpoint to an LLM service of your choosing

### Installation
1. Clone the repository:

```bash
    git clone https://github.com/yourusername/poormans-uxr.git
    cd poormans-uxr
```
2. Install the required packages:
```bash
pip install -r requirements.txt
```
3. Create a ```.streamlit``` directory and add a ```secrets.toml``` file:
```bash
mkdir -p .streamlit
touch .streamlit/secrets.toml
```
4. Add your API key and model configuration to the ```secrets.toml``` file:
```bash
api_key = "your_openai_api_key_here"
model_name = "gpt-4-turbo-preview"  # or your preferred model
```

### Running the application

Start the Streamlit server:
```bash
streamlit run app.py
```
The application will be available at ```http://localhost:8501``` in your web browser.

## Usage Guide

### Authentication
- **Create an Account:** Sign up with your email and password to save your projects
- **Guest Mode:** Alternatively, use the guest mode for quick exploration (projects can be transferred to a registered account later)

### Creating a project
1. Enter a description of your target user group (e.g., "University-enrolled engineering students")
2. Provide a general description of your product category (e.g., "A mobile app for collaborative note-taking")
3. The system will automatically generate a project name, which you can edit later

### Generating Personas
1. Click "Generate Persona Archetypes" to create broad user categories
2. Review and edit the generated archetypes as needed. You can also add more here.
3. Click "Generate Personas" to create specific personas based on these archetypes
4. Each persona will have a detailed background and characteristics relevant to your product. You can also edit these and add more as well.

### Simulating Interviews
1. The system automatically creates a UX Researcher persona to conduct interviews. However, you can edit this persona as well.
2. Click "Run" next to any persona to simulate an interview
3. Alternatively, use "Run All Remaining Interviews" to process multiple interviews in the background asynchronously
4. View completed interviews to see the conversation transcripts
5. NOTE: Running all interviews at once is more efficient but will make 10 calls to the LLM per interview. This process usually take 1-2 minutes.

### Analyzing Results
1. Click "Analyze" to process all interview data
2. The system will identify key themes and patterns across interviews
3. Review the generated insights and thematic clusters
4. NOTE: This process generally take 2-5 minutes depending on the results

### Generating Reports
1. Configure your report options (executive summary, key findings, recommendations, etc.)
2. Generate a comprehensive UX research report
3. Download the report in Markdown format for sharing with stakeholders

## Project Structure
- ```app.py:``` Main application entry point and UI logic
- ```uxr_app/:``` Core application modules
    - ```auth.py:``` Authentication functionality
    - ```database.py:``` Database models and operations
    - ```state.py:``` Application state management
- utils/: Utility functions
    - ```interview_utils.py:``` Interview simulation logic
    - ```convo_analysis.py:``` Conversation analysis tools
    - ```prompt_templates.py:``` LLM prompt templates

## Limitations
- AI-generated personas are not substitutes for real user research
- Results should be used for early exploration and hypothesis generation
- Findings should be validated with actual user testing when possible

## License
This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Acknowledgments
- Built with Streamlit, SQLAlchemy, Together AI API, and Mistral language models
- Inspired by the need for accessible UX research tools for small teams and startups