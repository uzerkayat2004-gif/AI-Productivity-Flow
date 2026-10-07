def get_prompt1_outline(knowledge_point, duration=5, reference_image_path=None):
    base_prompt = f""" 
    As an outstanding instructional design expert, design a logically clear, step-by-step, example-driven teaching outline.

    Knowledge Point: {knowledge_point}
    """

    # Add reference image guidance
    if reference_image_path:
        base_prompt += f"""

    ## Reference Image Available
    A reference image has been provided that relates to this knowledge point.

    ### How to Use the Reference Image for Outline Design:
    - Examine the key concepts, diagrams, and visual elements shown in the image
    - Identify which aspects of the knowledge point are emphasized or highlighted in the image
    - Design key section that can effectively utilize the visual concepts from the image
    - Prioritize sections that can benefit from the visual elements demonstrated in the image
    """

    base_prompt += f"""

    MUST output the teaching outline in JSON format as follows:
    {{
        "topic": "Topic Name",
        "target_audience": "Target Audience (e.g., high school students, university students, etc.)",
        "sections": [
            {{
                "id": "section_1",
                "title": "Section Title",
                "content": "Description of the section content",
                "example": "XXX"
            }},
            ...
        ]
    }}

    Requirements:
    1. The total duration should be fixed at around {duration} minutes.
    2. The sections should be arranged in a progressive and logical order.
    3. Emphasize key concepts and critical knowledge points.
    4. When presenting mathematical concepts, prefer representations that integrate graphical elements to enhance comprehension.
    5. The outline should be suitable for animation and visual presentation.
    6. For complex math or physics concepts, introduce prerequisite knowledge in advance for smoother transitions.
    7. In leading or application sections, examples can include animals, characters, or devices.
    """

    return base_prompt
