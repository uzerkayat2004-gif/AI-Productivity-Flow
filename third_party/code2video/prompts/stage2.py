import json


def get_prompt2_storyboard(outline, reference_image_path):

    base_prompt = f""" 
    You are a professional education Explainer and Animator, expert at converting mathematical teaching outlines into storyboard scripts suitable for the Manim animation system.

    ## Task
    Convert the following teaching outline into a detailed step-by-step storyboard script:

    {outline}
    """

    # Add reference image guidance
    if reference_image_path:
        base_prompt += f"""

    ## Reference Image Available
    A reference image has been provided to assist with designing the animations for this concept.

    ### How to Use the Reference Image:
    - Examine the visual elements, diagrams, layouts, and representations shown in the image
    - Use the image to inspire and guide your animation design, especially for the KEY SECTIONS
    - Focus on recreating the visual concepts using Manim objects (shapes, text, mathematical expressions)
    - Pay attention to how information is organized spatially in the image
    - If the image shows mathematical diagrams, design animations that build similar visualizations step by step
    - Use the image to identify which sections should have more detailed/complex animations
    - DO NOT reference the image directly in animations - instead recreate the concepts with Manim code
    
    ### Priority:
    - Give extra attention to sections that can benefit most from the visual concepts shown in the reference image
    """

    base_prompt += """
    ## Storyboard Requirements
    
    ### Content Structure
    - For key sections (max 3 sections), use up to 5 lecture lines along with their corresponding 5 animations to provide a logically coherent explanation. Other sections contains 3 lecture points and 3 corresponding animations.
    - In key sections, assets not forbiddened.
    - Must keep each lecture line brief [NO MORE THAN 10 WORDS FOR ONE LINE].
    - Animation steps must closely correspond to lecture points.
    - Do not apply any animation to lecture lines except for changing the color of corresponding line when its related animation is presented.

    ### Visual Design
    - Colors: Background fixed at #000000, use ligt color for contrast.
    - IMPORTANT: Provide hexadecimal codes for colors.
    - Element Labeling: Assign clear colors and labels near all elements (formulas, etc.).

    ### Animation Effects
    - Basic Animations: Appearance, movement, color changes, fade in/out, scaling.
    - Emphasis Effects: Flashing, color changes, bolding to highlight key knowledge points.

    ### Constraints
    - No panels or 3D methods.
    - Avoid coordinate axes unless absolutely necessary.
    - Focus animations on visualizing concepts that are difficult to grasp from lecture lines alone.
    - Ensure that all animations are easy to understand.
    - Do not involve any external elements (such as SVGs or other assets that require downloading or dependencies).

    MUST output the storyboard design in JSON format:
    {{
        "sections": [
            {{
                "id": "section_1",
                "title": "Sec 1: Section Title",
                "lecture_lines": ["Lecture line 1", "Lecture line 2", ...],
                "animations": [
                    "Animation step 1: ...",
                    "Animation step 2: ...",
                    ...
                ]
            }},
            ...
        ]
    }}
    """

    return base_prompt


def get_prompt_download_assets(storyboard_data):
    return f"""
Analyze this educational video storyboard and identify at most 4 different ESSENTIAL visual elements that MUST be represented with downloadable icons/images (not manually drawn shapes).

Content:
{storyboard_data}

Selection Criteria:
1. Only choose elements that appear in **introduction** or **application** sections, and that are:
   - Real-world, recognizable physical objects
   - Visually distinctive enough that a generic shape would not be sufficient
   - Concrete, not abstract concepts
2. Prioritize: specific animals, characters, vehicles, tools, devices, landmarks, everyday objects
3. IGNORE and NEVER include:
   - Abstract concepts (e.g., justice, communication)
   - Symbols or icons for ideas (e.g., letters, formulas, diagrams, trees in data structure)
   - Geometric shapes, arrows, or math-related visuals
   - Any object composed entirely of basic shapes without unique visual identity

Output format:
- Output ONLY the object keywords, each keyword must be one word, one per line, all lowercase, no numbering, no extra text.
"""


def get_prompt_place_assets(asset_mapping, animations_structure):
    return f"""
You need to enhance only the animations by incorporating downloaded assets where appropriate.

Asset list:
{asset_mapping}

Current Animations Data:
{animations_structure}

Instructions:
- For each animation, determine if any downloaded assets should be incorporated.
- Only choose the most relevant asset for the animation step that needs.
- Insert the **abstract path** of asset in the form: [Asset: XXX].
- CAN ONLY use the assets in **THE FIRST and THE LAST** sections.
- Keep the same structure: return an array with section_index, section_id, and enhanced animations.
- Only modify the animation descriptions to include asset references.
- Do not change section_index or section_id.

Return only the enhanced animations data as valid JSON array:
"""
