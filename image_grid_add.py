import os
import random
import pandas as pd
from flask import Flask, request, render_template_string, jsonify, make_response
from PIL import Image
import base64
import io
import json
from collections import Counter

# Initialize Flask App
app = Flask(__name__)

# Load Image Tags
def load_image_tags(tag_file):
    try:
        df = pd.read_csv(tag_file)
        if 'category' not in df.columns:
            df['category'] = ''
        return df
    except pd.errors.ParserError:
        print("Error reading CSV file. Please check the file format.")
        return pd.DataFrame(columns=['filename', 'category', 'tags'])

# Get Images by Tags
def get_images_by_tags(tags, image_tags_df):
    def tag_match(row_tags, search_tag):
        row_tag_list = set(row_tags.split('|'))
        return search_tag in row_tag_list

    selected_images = []
    tag_counts = Counter(tags)

    for tag, count in tag_counts.items():
        matching_images = image_tags_df[
            image_tags_df['tags'].apply(lambda x: tag_match(x, tag)) |
            (image_tags_df['category'] == tag)
            ]['filename'].tolist()

        if matching_images:
            selected_images.extend(random.sample(matching_images, min(count, len(matching_images))))

    return selected_images

# Randomly Fill Remaining Slots
def get_random_images(image_tags_df, exclude_list, count):
    available_images = image_tags_df[~image_tags_df['filename'].isin(exclude_list)]
    available_filenames = available_images['filename'].tolist()
    return random.sample(available_filenames, min(count, len(available_filenames)))

# Convert Image to Base64 String
def convert_image_to_base64(img_path):
    try:
        with Image.open(img_path) as img:
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except FileNotFoundError:
        print(f"Image file not found: {img_path}")
        return None
    except IOError:
        print(f"Error opening image file: {img_path}")
        return None

# Route to Log Interactions
@app.route('/log_interaction', methods=['POST'])
def log_interaction():
    data = request.get_json()
    session_csv = 'session_summary.csv'
    new_entry = pd.DataFrame([data])
    new_entry.to_csv(session_csv, mode='a', header=not os.path.exists(session_csv), index=False)
    return jsonify({"status": "success"})

# Home Route
@app.route('/', methods=['GET', 'POST'])
def home():
    # Load or Create Image Tag File
    tag_file = 'image_tags.csv'
    try:
        if not os.path.exists(tag_file):
            # Create a sample CSV if none exists
            sample_data = {'filename': ['cat.jpg', 'dog.jpg', 'car.jpg'],
                           'category': ['animals', 'animals', 'vehicles'],
                           'tags': ['animal|pet|cat', 'animal|pet|dog', 'vehicle|car']}
            pd.DataFrame(sample_data).to_csv(tag_file, index=False)

        image_tags_df = load_image_tags(tag_file)

        if image_tags_df.empty:
            return jsonify({"error": "empty_file", "message": "No valid data found in CSV file."})

    except FileNotFoundError:
        return jsonify({"error": "file_not_found", "message": "Image tag file not found."})

    if request.method == 'POST':
        # Parse form data
        antecedent_data = json.loads(request.form.get('antecedent_data', '[]'))
        behavior_data = json.loads(request.form.get('behavior_data', '{}'))
        consequence_data = json.loads(request.form.get('consequence_data', '{}'))

        grid_rows = int(request.form.get('grid_rows', 2))
        grid_cols = int(request.form.get('grid_cols', 2))

        selected_tags = [item['tag'] for item in antecedent_data if item['tag']]
        visible_tags = [item['tag'] for item in antecedent_data if item['tag'] and item['visible']]

        action_type = behavior_data.get('action_type', 'click')
        required_correct = int(behavior_data.get('required_correct', 1))

        # Parse Consequence Data
        enable_prompting = consequence_data.get('enable_prompting', False)
        use_prompt_delay = consequence_data.get('use_prompt_delay', False) if enable_prompting else False
        prompt_delay = float(consequence_data.get('prompt_delay', 0)) if use_prompt_delay else 0
        prompt_fade = consequence_data.get('prompt_fade', False) if enable_prompting else False
        prompt_highlight = consequence_data.get('prompt_highlight', False) if enable_prompting else False
        fade_duration = float(consequence_data.get('fade_duration', 1)) if consequence_data.get('fade_duration') else 1

        # Get fade percentage
        fade_percentage = int(consequence_data.get('fade_percentage', 40)) / 100  # Convert to decimal

        # Get highlight color
        highlight_color = consequence_data.get('highlight_color', '#28a745')  # Default to green

        # Reinforcement Option
        enable_reinforcement = consequence_data.get('enable_reinforcement', False)

        all_tags = set(image_tags_df['tags'].str.split('|').sum() + image_tags_df['category'].tolist())
        for tag in selected_tags:
            if tag not in all_tags:
                return jsonify(
                    {"error": "invalid_tag", "message": f"Error: Tag '{tag}' not found. Please enter valid tags."})

        # Get Selected and Random Images
        selected_images = get_images_by_tags(selected_tags, image_tags_df)
        total_needed = grid_rows * grid_cols

        if len(selected_images) < len(selected_tags):
            return jsonify({"error": "not_enough_images",
                            "message": f"Error: Not enough unique images found for the selected targets. Found {len(selected_images)} images for {len(selected_tags)} targets."})

        if len(selected_images) > total_needed:
            final_images = random.sample(selected_images, total_needed)
        else:
            final_images = selected_images
            remaining_count = total_needed - len(final_images)
            random_images = get_random_images(image_tags_df, final_images, remaining_count)
            final_images.extend(random_images)

        random.shuffle(final_images)

        # Store prompt settings to pass to the frontend
        prompt_settings = {
            'enable_prompting': enable_prompting,
            'use_prompt_delay': use_prompt_delay,
            'prompt_delay': prompt_delay,
            'prompt_fade': prompt_fade,
            'prompt_highlight': prompt_highlight,
            'fade_duration': fade_duration,
            'fade_percentage': fade_percentage,
            'highlight_color': highlight_color,
            'enable_reinforcement': enable_reinforcement
        }

        # Generate HTML for Image Grid
        grid_html = f"""
        <style>
            /* General Styles */
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
                background-color: #f0f2f5;
            }}
            #mainContent {{
                display: flex;
            }}
            #trialContainer {{
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            #endTrialBtn {{
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 10px 20px;
                background-color: #dc3545;
                color: #fff;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                z-index: 1000;
            }}
            #endTrialBtn:hover {{
                background-color: #c82333;
            }}
            #targetDropZones {{
                display: flex;
                justify-content: center;
                flex-wrap: wrap;
                margin-bottom: 20px;
                width: 100%;
            }}
            .target-drop-zone {{
                width: 150px;
                height: 150px;
                border: 2px dashed #6c757d;
                border-radius: 10px;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 10px;
                font-size: 1rem;
                color: #343a40;
                flex-direction: column;
                background-color: #ffffff;
                transition: border-color 0.3s;
            }}
            .target-drop-zone:hover {{
                border-color: #495057;
            }}
            .image-grid {{
                display: grid;
                grid-template-columns: repeat({grid_cols}, 250px);
                grid-gap: 15px;
                justify-content: center;
                align-content: center;
                margin: auto;
            }}
            .grid-image-container {{
                width: 250px;
                height: 250px;
                position: relative;
                overflow: hidden;
                border-radius: 15px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                background-color: #ffffff;
                transition: transform 0.2s;
            }}
            .grid-image-container:hover {{
                transform: scale(1.02);
            }}
            .grid-image {{
                width: 100%;
                height: 100%;
                object-fit: cover;
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }}
            .grid-image-container::after {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                border: 5px solid transparent;
                border-radius: 15px;
                transition: border-color 0.3s ease;
                pointer-events: none;
            }}
            .grid-image-container.correct::after {{
                border-color: #28a745;
            }}
            .grid-image-container.incorrect::after {{
                border-color: #dc3545;
            }}
            .draggable {{
                cursor: move;
            }}
            .dropped-image {{
                width: 100px;
                height: 100px;
                object-fit: cover;
                margin: 5px;
                border-radius: 10px;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
            }}
            /* Prompt Highlight Blinking Animation */
            @keyframes blink-border {{
                0% {{ border-color: {highlight_color}; }}
                50% {{ border-color: transparent; }}
                100% {{ border-color: {highlight_color}; }}
            }}
            .blink-border {{
                animation: blink-border 1s infinite;
            }}
            /* Prompt Fade Class */
            .prompt-fade {{
                opacity: {fade_percentage};
                transition: opacity {fade_duration}s ease;
            }}
        </style>
        <div id="mainContent">
            <div id="trialContainer">
                <button id="endTrialBtn">End Trial</button>
                <div id="targetDropZones">
        """
        for tag in visible_tags:
            grid_html += f"""
            <div class="target-drop-zone" data-target="{tag}">
                <strong>{tag}</strong>
            </div>
            """
        grid_html += """
                </div>
                <div class="image-grid">
        """
        for img_path in final_images:
            img_base64 = convert_image_to_base64(img_path)
            if img_base64:
                img_tags = set(image_tags_df[image_tags_df['filename'] == img_path]['tags'].iloc[0].split('|'))
                img_category = image_tags_df[image_tags_df['filename'] == img_path]['category'].iloc[0]
                img_tags.add(img_category)
                # Determine if the image is correct (matches any selected tag)
                is_correct = any(tag in img_tags for tag in selected_tags)
                data_correct = 'true' if is_correct else 'false'
                draggable_attr = 'true' if action_type == 'click_and_drag' else 'false'
                grid_html += f'''
                <div class="grid-image-container" 
                     draggable="{draggable_attr}"
                     data-correct="{data_correct}"
                     data-tags='{json.dumps(list(img_tags))}'
                     data-path='{img_path}'>
                    <img src="data:image/jpeg;base64,{img_base64}" class="grid-image draggable">
                </div>
                '''
        grid_html += """
                </div>
            </div>
        </div>
        """

        # Pass prompt settings and start time to the frontend
        grid_html += f"""
        <script>
            var promptSettings = {json.dumps(prompt_settings)};
            var startTime = Date.now();  // Record the start time
        </script>
        """

        response = make_response(render_template_string(grid_html + f"""
        <script>
        function initializeGrid(actionType, promptSettings) {{
            const {{
                enable_prompting,
                use_prompt_delay,
                prompt_delay,
                prompt_fade,
                prompt_highlight,
                enable_reinforcement
            }} = promptSettings;

            let interactionData = [];

            function handleAction(element, action, imgPath) {{
                const correctTags = JSON.parse(element.dataset.tags);
                const isCorrect = element.dataset.correct === 'true';
                const timeTaken = Date.now() - startTime;  // Calculate time taken
                logInteraction(element, imgPath, action, isCorrect, timeTaken);
                updateVisualFeedback(element, isCorrect);
            }}

            function updateVisualFeedback(element, isCorrect) {{
                if (enable_reinforcement) {{
                    element.classList.remove('correct', 'incorrect');
                    element.classList.add(isCorrect ? 'correct' : 'incorrect');
                }}
            }}

            function logInteraction(element, imgPath, action, isCorrect, timeTaken) {{
                const data = {{
                    timestamp: new Date().toISOString(),
                    image: imgPath,
                    action: action,
                    correct: isCorrect,
                    time_taken_ms: timeTaken,
                    tags: JSON.parse(element.dataset.tags),
                    prompt_settings: promptSettings
                }};
                interactionData.push(data);
                fetch('/log_interaction', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});
            }}

            function promptByExclusion() {{
                document.querySelectorAll('.grid-image-container[data-correct="false"]').forEach(container => {{
                    container.classList.add('prompt-fade');
                }});
            }}

            function promptByHighlighting() {{
                document.querySelectorAll('.grid-image-container[data-correct="true"]').forEach(container => {{
                    container.classList.add('blink-border');
                }});
            }}

            // Set up click handlers
            if (actionType === 'click' || actionType === 'click_and_drag') {{
                document.querySelectorAll('.grid-image-container').forEach(container => {{
                    container.addEventListener('click', function() {{
                        handleAction(this, 'click', this.dataset.path);
                    }});
                }});
            }}

            // Set up drag and drop functionality
            if (actionType === 'click_and_drag') {{
                const draggables = document.querySelectorAll('.draggable');
                const dropZones = document.querySelectorAll('.target-drop-zone');

                draggables.forEach(draggable => {{
                    draggable.addEventListener('dragstart', () => {{
                        draggable.classList.add('dragging');
                    }});

                    draggable.addEventListener('dragend', () => {{
                        draggable.classList.remove('dragging');
                    }});
                }});

                dropZones.forEach(dropZone => {{
                    dropZone.addEventListener('dragover', e => {{
                        e.preventDefault();
                    }});

                    dropZone.addEventListener('drop', e => {{
                        e.preventDefault();
                        const draggable = document.querySelector('.dragging');
                        if (draggable) {{
                            const container = draggable.closest('.grid-image-container');
                            const target = dropZone.dataset.target;
                            const imgTags = JSON.parse(container.dataset.tags);
                            const isCorrect = imgTags.includes(target);
                            const timeTaken = Date.now() - startTime;  // Calculate time taken
                            handleAction(container, 'drag', container.dataset.path);
                            if (isCorrect) {{
                                const img = draggable.cloneNode(true);
                                img.classList.remove('draggable', 'grid-image');
                                img.classList.add('dropped-image');
                                dropZone.appendChild(img);
                            }}
                        }}
                    }});
                }});
            }}

            // Handle Prompting Strategies after Delay
            if (enable_prompting && use_prompt_delay && prompt_delay > 0) {{
                setTimeout(() => {{
                    if (prompt_fade) {{
                        promptByExclusion();
                    }}
                    if (prompt_highlight) {{
                        promptByHighlighting();
                    }}
                }}, prompt_delay * 1000);  // Convert seconds to milliseconds
            }} else if (enable_prompting) {{
                // If no delay is set but prompting is enabled, apply prompts immediately
                if (prompt_fade) {{
                    promptByExclusion();
                }}
                if (prompt_highlight) {{
                    promptByHighlighting();
                }}
            }}

            // End Trial Button
            document.getElementById('endTrialBtn').addEventListener('click', function() {{
                showInteractionData();
            }});

            function showInteractionData() {{
                const dataStr = JSON.stringify(interactionData, null, 2);
                const pre = document.createElement('pre');
                pre.style.whiteSpace = 'pre-wrap';
                pre.textContent = dataStr;
                document.body.innerHTML = '';
                document.body.appendChild(pre);
            }}
        }}

        // Initialize the grid with action type and prompt settings
        initializeGrid('{action_type}', promptSettings);
        </script>
        """))

        response.headers['Content-Type'] = 'text/html'
        return response

    # Initial Form for User Input
    return """
    <style>
        /* General Styles */
        body { 
            font-family: Arial, sans-serif; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 20px; 
            box-sizing: border-box; 
            background-color: #e9ecef;
        }
        .container { 
            text-align: center; 
            font-size: 18px; 
            padding: 25px; 
            border: 1px solid #ced4da; 
            border-radius: 12px; 
            max-width: 700px; 
            width: 100%; 
            background-color: #ffffff;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        input[type="text"], input[type="number"], select { 
            font-size: 16px; 
            padding: 8px; 
            margin: 8px 0; 
            width: 100%; 
            box-sizing: border-box; 
            border: 1px solid #ced4da; 
            border-radius: 4px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, input[type="number"]:focus, select:focus { 
            border-color: #80bdff; 
            outline: none;
            box-shadow: 0 0 5px rgba(0, 123, 255, 0.5);
        }
        input[type="submit"] { 
            font-size: 18px; 
            padding: 12px 24px; 
            margin-top: 20px; 
            cursor: pointer; 
            background-color: #007bff; 
            color: white; 
            border: none; 
            border-radius: 6px; 
            transition: background-color 0.3s, transform 0.2s;
        }
        input[type="submit"]:hover { 
            background-color: #0056b3; 
            transform: translateY(-2px);
        }
        .number-input { 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            margin-bottom: 15px; 
        }
        .number-input button { 
            font-size: 20px; 
            padding: 6px 12px; 
            margin: 0 8px; 
            cursor: pointer; 
            background-color: #6c757d; 
            color: white; 
            border: none; 
            border-radius: 4px; 
            transition: background-color 0.3s, transform 0.2s;
        }
        .number-input button:hover { 
            background-color: #5a6268; 
            transform: translateY(-2px);
        }
        .target-input { 
            display: flex; 
            align-items: center; 
            margin-bottom: 12px; 
        }
        .target-input input[type="text"] { 
            flex-grow: 1; 
            margin-right: 10px; 
        }
        #addAntecedentBtn { 
            margin-top: 10px; 
            padding: 8px 16px; 
            background-color: #28a745; 
            color: white; 
            border: none; 
            border-radius: 4px; 
            cursor: pointer; 
            transition: background-color 0.3s, transform 0.2s;
        }
        #addAntecedentBtn:hover { 
            background-color: #218838; 
            transform: translateY(-2px);
        }
        .section { 
            border: 2px solid #007bff; 
            border-radius: 10px; 
            padding: 20px; 
            margin-bottom: 25px;
            background-color: #f8f9fa;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
        }
        .section h2 { 
            background-color: #007bff; 
            color: white; 
            padding: 12px; 
            margin: -20px -20px 20px -20px; 
            border-radius: 10px 10px 0 0;
        }

        /* Remove number input spinners */
        /* Chrome, Safari, Edge, Opera */
        input[type=number]::-webkit-inner-spin-button, 
        input[type=number]::-webkit-outer-spin-button { 
            -webkit-appearance: none; 
            margin: 0; 
        }

        /* Firefox */
        input[type=number] {
            -moz-appearance: textfield;
        }
    </style>
    <div class="container">
        <form method="POST" id="gridForm">
            <div class="section">
                <h2>Antecedent</h2>
                <div id="antecedentInputs">
                    <div class="target-input">
                        <input type="text" name="antecedent_tag" placeholder="Enter target" required>
                        <!-- 'Show target name' unchecked by default -->
                        <label><input type='checkbox' name='visible_target'> Show target name</label>
                    </div>
                </div>
                <button type="button" id="addAntecedentBtn">Add Another Target</button>
            </div>

            <div class="section">
                <h2>Behavior</h2>
                <div>
                    <label for="action_type">Action Type:</label>
                    <select name="action_type" id="action_type" required>
                        <option value="click">Click</option>
                        <option value="click_and_drag">Click and Drag to Match</option>
                    </select>
                </div>
                <div>
                    <label for="required_correct">Required Correct Responses:</label>
                    <input type="number" name="required_correct" id="required_correct" value="1" min="1" required>
                </div>
            </div>

            <div class="section">
                <h2>Consequence</h2>
                <!-- Reinforcement Subsection -->
                <div style="border: 1px solid #007bff; border-radius: 5px; padding: 10px; margin-bottom: 15px;">
                    <h3 style="margin-top: 0;">Reinforcement</h3>
                    <div>
                        <input type='checkbox' id='enable_reinforcement' name='enable_reinforcement'> Enable Green/Red Border Feedback
                    </div>
                </div>
                <div>
                    <!-- Enable Prompting Checkbox -->
                    <input type='checkbox' id='enable_prompting' name='enable_prompting'> Enable Prompting
                </div>
                <div id="promptingOptions" style="display:none;">
                    <div>
                        <input type='checkbox' id='use_prompt_delay' name='use_prompt_delay'> Use Prompt Delay
                    </div>
                    <div>
                        <label for="prompt_delay">Prompt Delay (seconds):</label>
                        <input type="number" id="prompt_delay" name="prompt_delay" min="0" max="10" step="0.1" value="0">
                    </div>
                    <div>
                        <input type='checkbox' id='prompt_fade' name='prompt_fade'> Prompt by Exclusion (Fade Incorrect Answers)
                    </div>
                    <!-- Fade Percentage Slider -->
                    <div id="fadePercentageContainer" style="display:none;">
                        <label for="fade_percentage">Prompt Fade Percentage (%):</label>
                        <input type="range" id="fade_percentage" name="fade_percentage" min="0" max="100" value="40">
                        <span id="fade_percentage_value">40%</span>
                    </div>
                    <div>
                        <input type='checkbox' id='prompt_highlight' name='prompt_highlight'> Prompt by Highlighting Correct Answer
                    </div>
                    <!-- Highlight Color Selector -->
                    <div id="highlightColorContainer" style="display:none;">
                        <label for="highlight_color">Prompt Highlight Color:</label>
                        <select id="highlight_color" name="highlight_color">
                            <option value="#28a745">Green</option> <!-- Default to Green -->
                            <option value="#FF0000">Red</option>
                            <option value="#FFA500">Orange</option>
                            <option value="#FFFF00">Yellow</option>
                            <option value="#0000FF">Blue</option>
                            <option value="#4B0082">Indigo</option>
                            <option value="#EE82EE">Violet</option>
                        </select>
                    </div>
                    <div>
                        <label for="fade_duration">Fade Duration (seconds):</label>
                        <input type="number" id="fade_duration" name="fade_duration" min="0.1" max="5" step="0.1" value="1">
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>Grid Configuration</h2>
                <div class="number-input">
                    Number of rows: 
                    <button type='button' onclick='adjustValue("grid_rows", -1)' aria-label="Decrease rows">-</button>
                    <input type="number" id="grid_rows" name="grid_rows" value="2" min="1" style="width: 40px; text-align: center;" readonly>
                    <button type='button' onclick='adjustValue("grid_rows", 1)' aria-label="Increase rows">+</button>
                </div>
                <div class="number-input">
                    Number of columns: 
                    <button type='button' onclick='adjustValue("grid_cols", -1)' aria-label="Decrease columns">-</button>
                    <input type="number" id="grid_cols" name="grid_cols" value="2" min="1" style="width: 40px; text-align: center;" readonly>
                    <button type='button' onclick='adjustValue("grid_cols", 1)' aria-label="Increase columns">+</button>
                </div>
            </div>

            <input type="hidden" id="antecedent_data" name="antecedent_data" value="[]">
            <input type="hidden" id="behavior_data" name="behavior_data" value="{}">
            <input type="hidden" id="consequence_data" name="consequence_data" value="{}">
            <input type="submit" value="Generate Grid">
        </form>
    </div>
    <script>
        function adjustValue(id, change) {
            const input = document.getElementById(id);
            const newValue = Math.max(1, parseInt(input.value) + change);
            input.value = newValue;
        }

        let antecedentCount = 1;
        document.getElementById('addAntecedentBtn').addEventListener('click', function() {
            const antecedentInputs = document.getElementById('antecedentInputs');
            const newInput = document.createElement('div');
            newInput.className = 'target-input';
            newInput.innerHTML = `
                <input type="text" name="antecedent_tag" placeholder="Enter target" required>
                <label><input type='checkbox' name='visible_target'> Show target name</label>
            `;
            antecedentInputs.appendChild(newInput);
            antecedentCount++;
        });

        // Auto-check 'Show target name' when 'Click and Drag to Match' is selected
        document.getElementById('action_type').addEventListener('change', function() {
            if (this.value === 'click_and_drag') {
                document.querySelectorAll('input[name="visible_target"]').forEach(function(checkbox) {
                    checkbox.checked = true;
                });
            }
        });

        // Show/hide prompting options
        document.getElementById('enable_prompting').addEventListener('change', function() {
            const promptingOptions = document.getElementById('promptingOptions');
            promptingOptions.style.display = this.checked ? 'block' : 'none';
        });

        // Show/hide fade percentage slider
        document.getElementById('prompt_fade').addEventListener('change', function() {
            document.getElementById('fadePercentageContainer').style.display = this.checked ? 'block' : 'none';
        });

        // Show/hide highlight color selector
        document.getElementById('prompt_highlight').addEventListener('change', function() {
            document.getElementById('highlightColorContainer').style.display = this.checked ? 'block' : 'none';
        });

        // Update displayed fade percentage
        document.getElementById('fade_percentage').addEventListener('input', function() {
            document.getElementById('fade_percentage_value').innerText = this.value + '%';
        });

        function prepareData() {
            // Prepare antecedent data
            const antecedentInputs = document.querySelectorAll('#antecedentInputs .target-input');
            const antecedentData = Array.from(antecedentInputs).map(input => ({
                tag: input.querySelector('input[name="antecedent_tag"]').value,
                visible: input.querySelector('input[name="visible_target"]').checked
            }));
            document.getElementById('antecedent_data').value = JSON.stringify(antecedentData);

            // Prepare behavior data
            const behaviorData = {
                action_type: document.getElementById('action_type').value,
                required_correct: document.getElementById('required_correct').value
            };
            document.getElementById('behavior_data').value = JSON.stringify(behaviorData);

            // Prepare consequence data
            const consequenceData = {
                enable_reinforcement: document.getElementById('enable_reinforcement').checked,
                enable_prompting: document.getElementById('enable_prompting').checked,
                use_prompt_delay: document.getElementById('use_prompt_delay').checked,
                prompt_delay: document.getElementById('prompt_delay').value,
                prompt_fade: document.getElementById('prompt_fade').checked,
                prompt_highlight: document.getElementById('prompt_highlight').checked,
                fade_duration: document.getElementById('fade_duration').value,
                fade_percentage: document.getElementById('fade_percentage').value,
                highlight_color: document.getElementById('highlight_color').value
            };
            document.getElementById('consequence_data').value = JSON.stringify(consequenceData);
        }

        document.getElementById('gridForm').addEventListener('submit', function(e) {
            e.preventDefault();
            prepareData();
            fetch('/', {
                method: 'POST',
                body: new FormData(this)
            })
            .then(response => {
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return response.json().then(data => ({ json: data }));
                } else {
                    return response.text().then(text => ({ html: text }));
                }
            })
            .then(data => {
                if (data.json) {
                    // Handle JSON response (error cases)
                    if (data.json.error === "file_not_found" || data.json.error === "empty_file") {
                        alert(data.json.message);
                    } else if (data.json.error === "invalid_tag") {
                        const inputs = document.querySelectorAll('input[name="antecedent_tag"]');
                        inputs.forEach(input => {
                            if (input.value === data.json.message.split("'")[1]) {
                                input.style.borderColor = 'red';
                            }
                        });
                        alert(data.json.message);
                    } else if (data.json.error === "not_enough_images") {
                        alert(data.json.message);
                    } else {
                        alert(data.json.message);
                    }
                } else if (data.html) {
                    // Handle HTML response (successful grid generation)
                    document.body.innerHTML = data.html;
                    // After setting innerHTML, run any embedded scripts
                    const scripts = document.body.getElementsByTagName("script");
                    for (let script of scripts) {
                        eval(script.innerHTML);
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An unexpected error occurred. Please try again.');
            });
        });
    </script>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
