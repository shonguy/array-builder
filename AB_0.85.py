import os
import random
import pandas as pd
from flask import Flask, request, render_template_string, jsonify, send_file
from PIL import Image
import base64
import io
import json
from collections import Counter
import uuid
import datetime

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

    for tag in tags:
        matching_images = image_tags_df[
            image_tags_df['tags'].apply(lambda x: tag_match(x, tag)) |
            (image_tags_df['category'] == tag)
            ]['filename'].tolist()

        if matching_images:
            selected_image = random.choice(matching_images)
            selected_images.append(selected_image)

    return selected_images


# Randomly Fill Remaining Slots
def get_random_images(image_tags_df, exclude_list, exclude_tags, count):
    def has_exclude_tag(row_tags):
        row_tag_list = set(row_tags.split('|'))
        return any(tag in row_tag_list for tag in exclude_tags)

    available_images = image_tags_df[~image_tags_df['filename'].isin(exclude_list)]
    # Exclude images that have any of the exclude_tags
    available_images = available_images[~available_images['tags'].apply(has_exclude_tag)]
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
    session_csv = f'session_{data["session_id"]}.csv'
    new_entry = pd.DataFrame([data])
    new_entry.to_csv(session_csv, mode='a', header=not os.path.exists(session_csv), index=False)
    return jsonify({"status": "success"})


# Route to Download Interaction Data
@app.route('/download_data/<session_id>')
def download_data(session_id):
    session_csv = f'session_{session_id}.csv'
    if os.path.exists(session_csv):
        return send_file(session_csv, as_attachment=True)
    else:
        return "No data available for this session."


# Home Route
@app.route('/', methods=['GET', 'POST'])
def home():
    # Generate a session ID
    session_id = str(uuid.uuid4())

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

        # Get image size from form
        image_size = int(request.form.get('image_size', 250))

        selected_tags = [item['tag'] for item in antecedent_data if item['tag']]
        visible_tags = [item['tag'] for item in antecedent_data if item['tag'] and item['visible']]

        action_type = behavior_data.get('action_type', 'click')
        required_correct = int(behavior_data.get('required_correct', 1))

        # Parse Consequence Data
        enable_prompting = consequence_data.get('enable_prompting', False)
        prompt_type = consequence_data.get('prompt_type', '') if enable_prompting else ''
        use_prompt_delay = consequence_data.get('use_prompt_delay', False) if enable_prompting else False
        prompt_delay = float(consequence_data.get('prompt_delay', 0)) if use_prompt_delay else 0
        fade_duration = float(consequence_data.get('fade_duration', 1)) if consequence_data.get('fade_duration') else 1

        # Get fade percentage
        fade_percentage = int(consequence_data.get('fade_percentage', 40)) / 100  # Convert to decimal

        # Get highlight color
        highlight_color = consequence_data.get('highlight_color', '#28a745')  # Default to green

        # Reinforcement Option
        enable_reinforcement = consequence_data.get('enable_reinforcement', False)
        enable_dance_animation = consequence_data.get('enable_dance_animation', False)

        # Sample Image Scale for MTS
        sample_image_scale = float(consequence_data.get('sample_image_scale', 0.5))  # Default to 0.5x

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
            random_images = get_random_images(image_tags_df, final_images, selected_tags, remaining_count)
            final_images.extend(random_images)

        random.shuffle(final_images)

        # Prepare image data for rendering
        image_data_list = []
        for img_path in final_images:
            img_base64 = convert_image_to_base64(img_path)
            if img_base64:
                img_tags = set(image_tags_df[image_tags_df['filename'] == img_path]['tags'].iloc[0].split('|'))
                img_category = image_tags_df[image_tags_df['filename'] == img_path]['category'].iloc[0]
                img_tags.add(img_category)
                # Determine if the image is correct (matches any selected tag)
                is_correct = any(tag in img_tags for tag in selected_tags)
                data_correct = 'true' if is_correct else 'false'
                draggable_attr = 'true' if action_type in ['click_and_drag', 'match_to_sample'] else 'false'
                image_data_list.append({
                    'img_base64': img_base64,
                    'img_tags': json.dumps(list(img_tags)),
                    'img_path': img_path,
                    'data_correct': data_correct,
                    'draggable_attr': draggable_attr,
                    'action_type': action_type
                })

        # Prepare sample images for Match to Sample
        sample_image_data = None
        if action_type == 'match_to_sample':
            # For simplicity, select a random correct image as the sample
            correct_images = [img for img in image_data_list if img['data_correct'] == 'true']
            if correct_images:
                sample_image = random.choice(correct_images)
                sample_image_data = {
                    'img_base64': sample_image['img_base64'],
                    'img_tags': sample_image['img_tags'],
                    'img_path': sample_image['img_path']
                }

        # Store prompt settings to pass to the frontend
        prompt_settings = {
            'enable_prompting': enable_prompting,
            'use_prompt_delay': use_prompt_delay,
            'prompt_delay': prompt_delay,
            'prompt_type': prompt_type,
            'fade_duration': fade_duration,
            'fade_percentage': fade_percentage,
            'highlight_color': highlight_color,
            'enable_reinforcement': enable_reinforcement,
            'enable_dance_animation': enable_dance_animation,
            'sample_image_scale': sample_image_scale
        }

        # Render the template with all necessary variables
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                /* General Styles */
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                    background-color: #f0f2f5;
                    overflow: hidden;
                }
                #mainContent {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    width: 100vw;
                    height: 100vh;
                    overflow: hidden;
                }
                #trialContainer {
                    width: 100%;
                    height: calc(100% - 60px);
                    max-width: 1200px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                }
                #endTrialBtn {
                    position: absolute;
                    top: 10px;
                    right: 10px;
                    padding: 10px 20px;
                    background-color: #dc3545;
                    color: #fff;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    z-index: 1000;
                }
                #endTrialBtn:hover {
                    background-color: #c82333;
                }
                #targetDropZones {
                    display: flex;
                    justify-content: center;
                    flex-wrap: wrap;
                    margin-bottom: 10px;
                    width: 100%;
                }
                .target-drop-zone {
                    width: 150px;
                    height: 150px;
                    border: 2px dashed #6c757d;
                    border-radius: 10px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    margin: 5px;
                    font-size: 1rem;
                    color: #343a40;
                    flex-direction: column;
                    background-color: #ffffff;
                    transition: border-color 0.3s;
                }
                .target-drop-zone:hover {
                    border-color: #495057;
                }
                .image-grid {
                    display: grid;
                    grid-template-columns: repeat({{ grid_cols }}, {{ image_size }}px);
                    grid-gap: 10px;
                    justify-content: center;
                    align-content: center;
                    margin: auto;
                }
                .grid-image-container {
                    width: {{ image_size }}px;
                    height: {{ image_size }}px;
                    position: relative;
                    overflow: hidden;
                    border-radius: 15px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    background-color: #ffffff;
                    transition: transform 0.2s;
                }
                .grid-image-container:hover {
                    transform: scale(1.02);
                }
                .grid-image {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                    -webkit-tap-highlight-color: transparent;
                }
                .grid-image-container::after {
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
                }
                .grid-image-container.correct::after {
                    border-color: #28a745;
                }
                .grid-image-container.incorrect::after {
                    border-color: #dc3545;
                }
                .draggable {
                    cursor: move;
                }
                .dropped-image {
                    width: 100px;
                    height: 100px;
                    object-fit: cover;
                    margin: 5px;
                    border-radius: 10px;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
                }
                /* Prompt Highlight Blinking Animation */
                @keyframes blink-border {
                    0% { border-color: currentColor; }
                    50% { border-color: transparent; }
                    100% { border-color: currentColor; }
                }
                .blink-border {
                     animation: blink-border 1s infinite;
                    border-style: solid;
                    border-width: 5px;
                    border-radius: 15px;
                }

                /* Prompt Fade Class */
                .prompt-fade {
                    opacity: {{ fade_percentage }};
                    transition: opacity {{ fade_duration }}s ease;
                }
                /* Manual Data Entry Buttons */
                #manualEntryButtons {
                    display: flex;
                    justify-content: center;
                    margin-top: 20px;
                }
                #manualEntryButtons button {
                    padding: 10px 20px;
                    font-size: 18px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    margin: 0 10px;
                    color: #fff;
                }
                #manualEntryButtons .correct-btn {
                    background-color: #28a745;
                }
                #manualEntryButtons .incorrect-btn {
                    background-color: #dc3545;
                }
                #manualEntryButtons button:hover {
                    opacity: 0.9;
                }
                /* Sample Image */
                #sampleImageContainer {
                    margin-bottom: 10px;
                    text-align: center;
                }
                #sampleImageContainer img {
                    width: calc({{ image_size }}px * {{ prompt_settings.sample_image_scale }});
                    height: calc({{ image_size }}px * {{ prompt_settings.sample_image_scale }});
                    object-fit: cover;
                    border-radius: 15px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    cursor: move;
                }
                /* Summary Modal */
                #summaryModal {
                    display: none;
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100vw;
                    height: 100vh;
                    background-color: rgba(0,0,0,0.5);
                    justify-content: center;
                    align-items: center;
                    z-index: 1001;
                }
                #summaryContent {
                    background-color: #fff;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    max-width: 500px;
                    width: 90%;
                }
                #summaryContent h2 {
                    margin-top: 0;
                }
                #summaryContent button {
                    margin-top: 20px;
                    padding: 10px 20px;
                    font-size: 16px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    color: #fff;
                    background-color: #007bff;
                }
                #summaryContent button:hover {
                    background-color: #0056b3;
                }
                /* Responsive Adjustments */
                @media (max-height: 700px) {
                    .grid-image-container {
                        width: calc({{ image_size }}px * 0.8);
                        height: calc({{ image_size }}px * 0.8);
                    }
                    .image-grid {
                        grid-template-columns: repeat({{ grid_cols }}, calc({{ image_size }}px * 0.8));
                    }
                    #sampleImageContainer img {
                        width: calc({{ image_size }}px * {{ prompt_settings.sample_image_scale }} * 0.8);
                        height: calc({{ image_size }}px * {{ prompt_settings.sample_image_scale }} * 0.8);
                    }
                }
                /* Dance Animation */
                @keyframes dance {
                    0% { transform: rotate(0deg); }
                    25% { transform: rotate(10deg); }
                    50% { transform: rotate(-10deg); }
                    75% { transform: rotate(10deg); }
                    100% { transform: rotate(0deg); }
                }

                .dance-animation {
                    animation: dance 0.5s ease-in-out;
                }

            </style>
        </head>
        <body>
            <div id="mainContent">
                <button id="endTrialBtn">End Trial</button>
                <div id="trialContainer">
                    {% if action_type == 'match_to_sample' and sample_image_data %}
                    <div id="sampleImageContainer">
                        <h3>Sample Image:</h3>
                        <img src="data:image/jpeg;base64,{{ sample_image_data.img_base64 }}" id="sampleImage" draggable="true" data-tags='{{ sample_image_data.img_tags }}'>
                    </div>
                    {% endif %}
                    {% if visible_tags %}
                    <div id="targetDropZones">
                        {% for tag in visible_tags %}
                        <div class="target-drop-zone" data-target="{{ tag }}">
                            <strong>{{ tag }}</strong>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                    <div class="image-grid">
                        {% for image in image_data_list %}
                        <div class="grid-image-container" 
                             data-correct="{{ image.data_correct }}"
                             data-tags='{{ image.img_tags }}'
                             data-path='{{ image.img_path }}'>
                            <img src="data:image/jpeg;base64,{{ image.img_base64 }}" class="grid-image">
                        </div>
                        {% endfor %}
                    </div>
                    {% if action_type == 'manual_data_entry' %}
                    <div id="manualEntryButtons">
                        <button class="correct-btn">✔️ Correct</button>
                        <button class="incorrect-btn">✖️ Incorrect</button>
                    </div>
                    {% endif %}
                </div>
            </div>
            <!-- Summary Modal -->
            <div id="summaryModal">
                <div id="summaryContent">
                    <h2>Session Summary</h2>
                    <p id="summaryText"></p>
                    <button id="downloadDataBtn">Download Detailed Data</button>
                    <button id="returnToConfigBtn">Return to Configuration</button>
                </div>
            </div>
            <script>
                var promptSettings = {{ prompt_settings | tojson }};
                var startTime = Date.now();  // Record the start time
                var sessionId = '{{ session_id }}';
                var trialNumber = 0;
</script>

            <script>
            function initializeGrid(actionType, promptSettings) {
                const {
                    enable_prompting,
                    use_prompt_delay,
                    prompt_delay,
                    prompt_type,
                    fade_duration,
                    fade_percentage,
                    highlight_color,
                    enable_reinforcement,
                    enable_dance_animation,
                    sample_image_scale
                } = promptSettings;

                let interactionData = [];

                function handleAction(element, action, imgPath, isCorrect, promptUsed) {
                    const timeTaken = Date.now() - startTime;  // Calculate time taken
                    trialNumber++;
                    logInteraction(element, imgPath, action, isCorrect, timeTaken, promptUsed);
                    if (element && enable_reinforcement) {
                        updateVisualFeedback(element, isCorrect);
                    }
                }

                function updateVisualFeedback(element, isCorrect) {
                    element.classList.remove('correct', 'incorrect', 'dance-animation');
                    element.classList.add(isCorrect ? 'correct' : 'incorrect');
    
                    if (isCorrect && enable_dance_animation) {
                        element.classList.add('dance-animation');
                        // Remove the dance-animation class after the animation ends to allow re-triggering
                        element.addEventListener('animationend', function() {
                            element.classList.remove('dance-animation');
                        }, { once: true });
                    }
                }

                function logInteraction(element, imgPath, action, isCorrect, timeTaken, promptUsed) {
                    const data = {
                        session_id: sessionId,
                        trial_number: trialNumber,
                        timestamp: new Date().toISOString(),
                        target_name: getTargetName(imgPath),
                        image_file_name: imgPath || 'N/A',
                        time_taken_ms: timeTaken,
                        prompt_used: promptUsed || 'None',
                        correct: isCorrect ? 'Correct' : 'Incorrect'
                    };
                    interactionData.push(data);
                    fetch('/log_interaction', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });
                }

                function getTargetName(imgPath) {
                    if (!imgPath) return 'N/A';
                    const container = document.querySelector(`.grid-image-container[data-path='${imgPath}']`);
                    const tags = JSON.parse(container.dataset.tags);
                    return tags.find(tag => {{ selected_tags | tojson }}.includes(tag)) || 'Unknown';
                }

                function promptByExclusion() {
                    document.querySelectorAll('.grid-image-container[data-correct="false"]').forEach(container => {
                        container.classList.add('prompt-fade');
                    });
                }

                function promptByHighlighting() {
                    document.querySelectorAll('.grid-image-container[data-correct="true"]').forEach(container => {
                        container.style.color = promptSettings.highlight_color; // Set currentColor
                        container.style.borderColor = promptSettings.highlight_color;
                        container.classList.add('blink-border');
                    });
                }


                // Set up interaction handlers based on action type
                if (actionType === 'click') {
                    document.querySelectorAll('.grid-image-container').forEach(container => {
                        container.addEventListener('click', function() {
                            handleAction(this, 'click', this.dataset.path, this.dataset.correct === 'true', prompt_type || 'None');
                        });
                    });
                } else if (actionType === 'click_and_drag') {
                    // Set up drag and drop functionality
                    const draggables = document.querySelectorAll('.grid-image');
                    const dropZones = document.querySelectorAll('.target-drop-zone');

                    draggables.forEach(draggable => {
                        draggable.setAttribute('draggable', 'true');
                        draggable.addEventListener('dragstart', () => {
                            draggable.classList.add('dragging');
                        });

                        draggable.addEventListener('dragend', () => {
                            draggable.classList.remove('dragging');
                        });
                    });

                    dropZones.forEach(dropZone => {
                        dropZone.addEventListener('dragover', e => {
                            e.preventDefault();
                        });

                        dropZone.addEventListener('drop', e => {
                            e.preventDefault();
                            const draggable = document.querySelector('.dragging');
                            if (draggable) {
                                const container = draggable.closest('.grid-image-container');
                                const target = dropZone.dataset.target;
                                const imgTags = JSON.parse(container.dataset.tags);
                                const isCorrect = imgTags.includes(target);
                                const timeTaken = Date.now() - startTime;  // Calculate time taken
                                handleAction(container, 'drag', container.dataset.path, isCorrect, prompt_type || 'None');
                                if (isCorrect) {
                                    const img = draggable.cloneNode(true);
                                    img.classList.remove('draggable', 'grid-image');
                                    img.classList.add('dropped-image');
                                    dropZone.appendChild(img);
                                }
                            }
                        });
                    });
                } else if (actionType === 'manual_data_entry') {
                    // Images are not interactive
                    const correctBtn = document.querySelector('#manualEntryButtons .correct-btn');
                    const incorrectBtn = document.querySelector('#manualEntryButtons .incorrect-btn');

                    correctBtn.addEventListener('click', function() {
                        handleAction(null, 'manual_entry', null, true, prompt_type || 'None');
                    });

                    incorrectBtn.addEventListener('click', function() {
                        handleAction(null, 'manual_entry', null, false, prompt_type || 'None');
                    });
                } else if (actionType === 'match_to_sample') {
                    // Match to Sample functionality
                    const sampleImage = document.getElementById('sampleImage');
                    const targetContainers = document.querySelectorAll('.grid-image-container');
                    sampleImage.addEventListener('dragstart', () => {
                        sampleImage.classList.add('dragging');
                    });
                    sampleImage.addEventListener('dragend', () => {
                        sampleImage.classList.remove('dragging');
                    });
                    targetContainers.forEach(container => {
                        container.addEventListener('dragover', e => {
                            e.preventDefault();
                        });
                        container.addEventListener('drop', e => {
                            e.preventDefault();
                            if (sampleImage.classList.contains('dragging')) {
                                const isCorrect = container.dataset.correct === 'true';
                                handleAction(container, 'match_to_sample', container.dataset.path, isCorrect, prompt_type || 'None');
                                if (enable_reinforcement) {
                                    updateVisualFeedback(container, isCorrect);
                                }
                            }
                        });
                    });
                }

                // Handle Prompting Strategies after Delay
                if (enable_prompting && use_prompt_delay && prompt_delay > 0) {
                    setTimeout(() => {
                        applyPrompt();
                    }, prompt_delay * 1000);  // Convert seconds to milliseconds
                } else if (enable_prompting) {
                    applyPrompt();
                }

                function applyPrompt() {
                    if (prompt_type === 'fade') {
                        promptByExclusion();
                    } else if (prompt_type === 'highlight') {
                        promptByHighlighting();
                    }
                }

                // End Trial Button
                document.getElementById('endTrialBtn').addEventListener('click', function() {
                    showSummary();
                });

                function showSummary() {
                    // Calculate summary data
                    const totalTrials = interactionData.length;
                    const correctResponses = interactionData.filter(d => d.correct === 'Correct').length;
                    const incorrectResponses = totalTrials - correctResponses;
                    const accuracy = ((correctResponses / totalTrials) * 100).toFixed(2);

                    // Display summary
                    document.getElementById('summaryText').innerHTML = `
                        Total Trials: ${totalTrials}<br>
                        Correct Responses: ${correctResponses}<br>
                        Incorrect Responses: ${incorrectResponses}<br>
                        Accuracy: ${accuracy}%
                    `;
                    document.getElementById('summaryModal').style.display = 'flex';

                    // Download Data Button
                    document.getElementById('downloadDataBtn').addEventListener('click', function() {
                        window.location.href = '/download_data/' + sessionId;
                    });
                    // Return to Configuration Button
                    document.getElementById('returnToConfigBtn').addEventListener('click', function() {
                        window.location.href = '/';
                    });

                }

                // Close summary modal on click outside
                window.addEventListener('click', function(event) {
                    if (event.target == document.getElementById('summaryModal')) {
                        document.getElementById('summaryModal').style.display = 'none';
                    }
                });
            }

            // Initialize the grid with action type and prompt settings
            initializeGrid('{{ action_type }}', promptSettings);
            </script>
        </body>
        </html>
        ''', grid_cols=grid_cols,
                                      fade_percentage=fade_percentage,
                                      fade_duration=fade_duration,
                                      highlight_color=highlight_color,
                                      visible_tags=visible_tags,
                                      image_data_list=image_data_list,
                                      action_type=action_type,
                                      prompt_settings=prompt_settings,
                                      selected_tags=selected_tags,
                                      image_size=image_size,
                                      sample_image_data=sample_image_data,
                                      session_id=session_id)

    # Initial Form for User Input
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            /* General Styles */
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; 
                padding: 20px; 
                box-sizing: border-box; 
                background-color: #e9ecef;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
            }
            .form-container {
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
            }
            .section { 
                border: 2px solid #007bff; 
                border-radius: 10px; 
                padding: 20px; 
                margin-bottom: 25px;
                background-color: #f8f9fa;
                box-sizing: border-box;
                flex: 1 1 calc(33% - 20px);
                margin: 10px;
            }
            .section h2 { 
                background-color: #007bff; 
                color: white; 
                padding: 12px; 
                margin: -20px -20px 20px -20px; 
                border-radius: 10px 10px 0 0;
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
            /* Advanced Settings */
            #advancedSettingsToggle {
                margin-top: 20px;
                cursor: pointer;
                color: #007bff;
                text-decoration: underline;
            }
            #advancedSettingsContent {
                display: none;
                margin-top: 10px;
            }
            @media (max-width: 768px) {
                .section {
                    flex: 1 1 100%;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <form method="POST" id="gridForm">
                <div class="form-container">
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
                        <!-- Image Size Input -->
                        <div>
                            <label for="image_size">Image Size (pixels):</label>
                            <input type="number" id="image_size" name="image_size" value="250" min="50" max="1000" required>
                        </div>
                        <!-- Grid Configuration -->
                        <h3 style="margin-top: 20px;">Grid Configuration</h3>
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

                    <div class="section">
                        <h2>Behavior</h2>
                        <div>
                            <label for="action_type">Action Type:</label>
                            <select name="action_type" id="action_type" required>
                                <option value="click">Click</option>
                                <option value="click_and_drag">Click and Drag to Match</option>
                                <option value="match_to_sample">Match to Sample (MTS)</option>
                                <option value="manual_data_entry">Manual Data Entry</option>
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
                        <div>
                            <input type='checkbox' id='enable_reinforcement' name='enable_reinforcement' checked> Enable Green/Red Border Feedback
                        </div>
                        <!-- Advanced Settings Toggle -->
                        <div id="advancedSettingsToggle">Show Advanced Settings</div>
                        <div id="advancedSettingsContent">
                            <!-- Reinforcement Options -->
                            <div style="border: 1px solid #007bff; border-radius: 5px; padding: 10px; margin-top: 10px;">
                                <h3 style="margin-top: 0;">Reinforcement Options</h3>
                                <div>
                                    <input type='checkbox' id='enable_dance_animation' name='enable_dance_animation'>
                                    <label for='enable_dance_animation'>Enable Dance Animation on Correct Answer</label>
                                </div>
                                <div>
                                    <input type='checkbox' id='enable_image_spinning' name='enable_image_spinning'>
                                    <label for='enable_image_spinning'>Enable Image Spinning on Correct Answer</label>
                            </div>
                        </div>

                            <div style="border: 1px solid #007bff; border-radius: 5px; padding: 10px; margin-top: 10px;">
                                <h3 style="margin-top: 0;">Prompting Options</h3>
                                <div>
                                    <!-- Enable Prompting Checkbox -->
                                    <input type='checkbox' id='enable_prompting' name='enable_prompting'> Enable Prompting
                                </div>
                                <div id="promptingOptions" style="display:none;">
                                    <!-- Prompt Type Radio Buttons -->
                                    <div>
                                        <label><input type="radio" name="prompt_type" value="fade" checked> Prompt by Exclusion (Fade Incorrect Answers)</label>
                                    </div>
                                    <div>
                                        <!-- Fade Percentage Slider -->
                                        <div id="fadePercentageContainer">
                                            <label for="fade_percentage">Prompt Fade Percentage (%):</label>
                                            <input type="range" id="fade_percentage" name="fade_percentage" min="0" max="100" value="40">
                                            <span id="fade_percentage_value">40%</span>
                                        </div>
                                    </div>
                                    <div>
                                        <label><input type="radio" name="prompt_type" value="highlight"> Prompt by Highlighting Correct Answer</label>
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
                                        <input type='checkbox' id='use_prompt_delay' name='use_prompt_delay'> Use Prompt Delay
                                    </div>
                                    <div>
                                        <label for="prompt_delay">Prompt Delay (seconds):</label>
                                        <input type="number" id="prompt_delay" name="prompt_delay" min="0" max="10" step="0.1" value="0">
                                    </div>
                                    <div>
                                        <label for="fade_duration">Fade Duration (seconds):</label>
                                        <input type="number" id="fade_duration" name="fade_duration" min="0.1" max="5" step="0.1" value="1">
                                    </div>
                                </div>
                                <!-- Sample Image Scale for MTS -->
                                <div id="mtsOptions" style="display:none; margin-top: 10px;">
                                    <h3 style="margin-top: 0;">Match to Sample Options</h3>
                                    <div>
                                        <label for="sample_image_scale">Sample Image Scale (0.2x to 1.0x):</label>
                                        <input type="range" id="sample_image_scale" name="sample_image_scale" min="0.2" max="1.0" step="0.1" value="0.5">
                                        <span id="sample_image_scale_value">0.5x</span>
                                    </div>
                                </div>
                            </div>
                        </div>
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
                if (this.value === 'click_and_drag' || this.value === 'match_to_sample') {
                    document.querySelectorAll('input[name="visible_target"]').forEach(function(checkbox) {
                        checkbox.checked = true;
                    });
                } else if (this.value === 'manual_data_entry') {
                    // Hide 'Show target name' checkboxes
                    document.querySelectorAll('input[name="visible_target"]').forEach(function(checkbox) {
                        checkbox.checked = false;
                        checkbox.parentElement.style.display = 'none';
                    });
                } else {
                    // Show 'Show target name' checkboxes
                    document.querySelectorAll('input[name="visible_target"]').forEach(function(checkbox) {
                        checkbox.parentElement.style.display = 'inline-block';
                    });
                }

                // Show/hide MTS options
                const mtsOptions = document.getElementById('mtsOptions');
                if (this.value === 'match_to_sample') {
                    mtsOptions.style.display = 'block';
                } else {
                    mtsOptions.style.display = 'none';
                }
            });

            // Show/hide prompting options
            document.getElementById('enable_prompting').addEventListener('change', function() {
                const promptingOptions = document.getElementById('promptingOptions');
                promptingOptions.style.display = this.checked ? 'block' : 'none';
            });

            // Show/hide specific prompt options based on selected prompt type
            document.querySelectorAll('input[name="prompt_type"]').forEach(function(radio) {
                radio.addEventListener('change', function() {
                    if (this.value === 'fade') {
                        document.getElementById('fadePercentageContainer').style.display = 'block';
                        document.getElementById('highlightColorContainer').style.display = 'none';
                    } else if (this.value === 'highlight') {
                        document.getElementById('fadePercentageContainer').style.display = 'none';
                        document.getElementById('highlightColorContainer').style.display = 'block';
                    }
                });
            });

            // Update displayed fade percentage
            document.getElementById('fade_percentage').addEventListener('input', function() {
                document.getElementById('fade_percentage_value').innerText = this.value + '%';
            });

            // Update displayed sample image scale
            document.getElementById('sample_image_scale').addEventListener('input', function() {
                document.getElementById('sample_image_scale_value').innerText = this.value + 'x';
            });

            // Advanced Settings Toggle
            document.getElementById('advancedSettingsToggle').addEventListener('click', function() {
                const advancedContent = document.getElementById('advancedSettingsContent');
                if (advancedContent.style.display === 'none' || advancedContent.style.display === '') {
                    advancedContent.style.display = 'block';
                    this.innerText = 'Hide Advanced Settings';
                } else {
                    advancedContent.style.display = 'none';
                    this.innerText = 'Show Advanced Settings';
                }
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
                    enable_dance_animation: document.getElementById('enable_dance_animation').checked,
                    enable_prompting: document.getElementById('enable_prompting').checked,
                    prompt_type: document.querySelector('input[name="prompt_type"]:checked') ? document.querySelector('input[name="prompt_type"]:checked').value : '',
                    use_prompt_delay: document.getElementById('use_prompt_delay').checked,
                    prompt_delay: document.getElementById('prompt_delay').value,
                    fade_duration: document.getElementById('fade_duration').value,
                    fade_percentage: document.getElementById('fade_percentage').value,
                    highlight_color: document.getElementById('highlight_color').value,
                    sample_image_scale: document.getElementById('sample_image_scale').value
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
    </body>
    </html>
    '''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
