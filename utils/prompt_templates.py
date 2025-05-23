def get_project_name_prompt(user_group_desc, product_desc):
    return f"""
    Generate a concise and modern project name based on:
    User group: {user_group_desc}
    Product Type: {product_desc}
    Respond only with the project name. 

    Project name:
    """

def get_persona_archetypes_prompt(user_group_desc, product_desc):
    return f"""
    Generate 7 persona archetypes based on:
    User group: {user_group_desc}
    Product: {product_desc}
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

def get_specific_persona_prompt(archetype_name, archetype_desc, existing_names, product_desc):
    return f"""
    Generate a specific user persona based on this archetype:
    {archetype_name}: {archetype_desc}

    For the following general product description:
    {product_desc}

    Create a clear, complete, and well-structured description of the persona with the following sections:
    - Name: [Unique name of the persona. Ensure this name is not used for any other persona in this project. 
         Existing persona names: {', '.join(existing_names)}].
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

    Respond in the following format:
    <name> [Persona name] </name>
    <age> [Age] </age>
    <demographics> [Demographics] </demographics>
    <location> [Location] </location>
    <motivations> [Motivations] </motivations>
    <goals_needs> [Goals and needs] </goals_needs>
    <values> [Values] </values>
    <attitudes_beliefs> [Attitudes and beliefs] </attitudes_beliefs>
    <lifestyle> [Lifestyle] </lifestyle>
    <daily_routine> [Daily routine] </daily_routine>
    <devise_usage> [Devise usage] </devise_usage>
    <software_familiarity> [Software familiarity] </software_familiarity>
    <digital_literacy> [Digital literacy] </digital_literacy>
    <pain_points> [Pain points] </pain_points>
    <delightful_moments> [Delightful moments] </delightful_moments>
    """

def parse_persona_response(response):
    name = response.split("<name>")[1].split("</name>")[0].strip() if "<name>" in response else None
    age = response.split("<age>")[1].split("</age>")[0].strip() if "<age>" in response else None
    demographics = response.split("<demographics>")[1].split("</demographics>")[0].strip() if "<demographics>" in response else None
    location = response.split("<location>")[1].split("</location>")[0].strip() if "<location>" in response else None
    motivations = response.split("<motivations>")[1].split("</motivations>")[0].strip() if "<motivations>" in response else None
    goals_needs = response.split("<goals_needs>")[1].split("</goals_needs>")[0].strip() if "<goals_needs>" in response else None
    values = response.split("<values>")[1].split("</values>")[0].strip() if "<values>" in response else None
    attitudes_beliefs = response.split("<attitudes_beliefs>")[1].split("</attitudes_beliefs>")[0].strip() if "<attitudes_beliefs>" in response else None
    lifestyle = response.split("<lifestyle>")[1].split("</lifestyle>")[0].strip() if "<lifestyle>" in response else None
    daily_routine = response.split("<daily_routine>")[1].split("</daily_routine>")[0].strip() if "<daily_routine>" in response else None
    devise_usage = response.split("<devise_usage>")[1].split("</devise_usage>")[0].strip() if "<devise_usage>" in response else None
    software_familiarity = response.split("<software_familiarity>")[1].split("</software_familiarity>")[0].strip() if "<software_familiarity>" in response else None
    digital_literacy = response.split("<digital_literacy>")[1].split("</digital_literacy>")[0].strip() if "<digital_literacy>" in response else None
    pain_points = response.split("<pain_points>")[1].split("</pain_points>")[0].strip() if "<pain_points>" in response else None
    delightful_moments = response.split("<delightful_moments>")[1].split("</delightful_moments>")[0].strip() if "<delightful_moments>" in response else None
    output = {
        "name": name,
        "age": age,
        "demographics": demographics,
        "location": location,
        "motivations": motivations,
        "goals_needs": goals_needs,
        "values": values,
        "attitudes_beliefs": attitudes_beliefs,
        "lifestyle": lifestyle,
        "daily_routine": daily_routine,
        "devise_usage": devise_usage,
        "software_familiarity": software_familiarity,
        "digital_literacy": digital_literacy,
        "pain_points": pain_points,
        "delightful_moments": delightful_moments
    }
    desc = [f"{k.capitalize().replace('_', ' ')}: {v}" for k, v in output.items() if v]
    output["description"] = "\n".join(desc)
    return output


def get_exec_summary_prompt(product_desc, user_group_desc, themes):
    return f"""
    Create an executive summary for a UX research report based on the following:
    
    PRODUCT:
    {product_desc}
    
    USER GROUP:
    {user_group_desc}

    KEY THEMES:
    {', '.join(themes)}
    
    The executive summary should be concise (150-250 words) and highlight the most important findings
    and recommendations. Focus on insights that would be most valuable for product development.

    Respond only with the executive summary in markdown format.

    EXECUTIVE SUMMARY:
    """

def get_recommendations_prompt(product_desc, user_group_desc, themes_json):
    return f"""
    Create a "Recommendations" section for a UX research report based on these research findings:
    
    PRODUCT:
    {product_desc}

    USER GROUP:
    {user_group_desc}

    KEY THEMES:
    {themes_json}
    
    Provide 5-7 specific, actionable recommendations that:
    1. Address the key pain points identified
    2. Leverage the opportunities discovered
    3. Are realistic to implement
    
    Format each recommendation with:
    - A clear, actionable title
    - A brief explanation of the recommendation
    - The expected impact or benefit
    
    Respond only with the recommendations in markdown format.

    RECOMMENDATIONS:
    """

def get_findings_prompt(summaries_json):
    return f"""
    Create a "Key Findings" section for a UX research report based on these themes:
    
    {summaries_json}
    
    For each theme, provide:
    1. A clear headline that captures the essence of the finding
    2. A brief explanation (2-3 sentences)
    3. The potential impact on the product design
    
    Format each finding as a separate section with markdown formatting.
    """

def get_demographics_prompt(persona_desc):
    return f"""
    Extract and summarize the key demographic information from this persona description in 3-4 sentences:
    
    {persona_desc}
    
    Focus only on demographics, age, location, and background. Be concise.
    """