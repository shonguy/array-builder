import os
import random
import pandas as pd
from flask import Flask, request, render_template, jsonify, send_file
from PIL import Image
import base64
import io
import json
import uuid
import time

# Initialize Flask App
app = Flask(__name__, static_folder='static', static_url_path='/static')

# Debug route to check static file paths
@app.route('/debug/static')
def debug_static():
    js_path = os.path.join(app.static_folder, 'js', 'grid.js')
    css_path = os.path.join(app.static_folder, 'css', 'styles.css')
    return {
        'static_folder': app.static_folder,
        'static_url_path': app.static_url_path,
        'js_exists': os.path.exists(js_path),
        'css_exists': os.path.exists(css_path),
        'js_path': js_path,
        'css_path': css_path
    }

# Set the path to the images directory (relative to the script location)
IMAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images'))
TAG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'image_tags.csv'))

# Load Image Tags
def load_image_tags(tag_file):
    try:
        df = pd.read_csv(tag_file)
        print(f"Loaded {len(df)} rows from {tag_file}")
        print(f"Columns found: {df.columns.tolist()}")
        
        # Ensure required columns exist
        if 'filename' not in df.columns:
            print("Error: 'filename' column not found in CSV")
            return pd.DataFrame(columns=['filename', 'category', 'tags'])
            
        if 'tags' not in df.columns:
            print("Error: 'tags' column not found in CSV")
            return pd.DataFrame(columns=['filename', 'category', 'tags'])
            
        if 'category' not in df.columns:
            print("Adding empty 'category' column")
            df['category'] = ''
            
        # Print some sample data
        print("\nFirst few rows of the dataframe:")
        print(df.head())
        
        return df
    except pd.errors.ParserError as e:
        print(f"Error reading CSV file: {e}")
        return pd.DataFrame(columns=['filename', 'category', 'tags'])
    except Exception as e:
        print(f"Unexpected error reading CSV file: {e}")
        return pd.DataFrame(columns=['filename', 'category', 'tags'])

# Get Images by Tags
def get_images_by_tags(tags, image_tags_df):
    def tag_match(row_tags, search_tag):
        row_tag_list = set(row_tags.split('|'))
        return search_tag in row_tag_list

    selected_images = []
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
        if pd.isna(row_tags):  # Handle NaN values
            return False
        row_tag_list = set(row_tags.split('|'))
        return any(tag in row_tag_list for tag in exclude_tags)

    available_images = image_tags_df[~image_tags_df['filename'].isin(exclude_list)]
    available_images = available_images[~available_images['tags'].apply(has_exclude_tag)]
    available_filenames = available_images['filename'].tolist()
    
    if not available_filenames:  # If no available images, print debug info
        print("No available images for distractors. Debug info:")
        print(f"Total images in df: {len(image_tags_df)}")
        print(f"Images after exclude list: {len(image_tags_df[~image_tags_df['filename'].isin(exclude_list)])}")
        print(f"Exclude tags: {exclude_tags}")
        return []
        
    try:
        return random.sample(available_filenames, min(count, len(available_filenames)))
    except ValueError as e:
        print(f"Error sampling images: {e}")
        print(f"Available filenames: {available_filenames}")
        print(f"Count requested: {count}")
        return []

# Convert Image to Base64 String
def convert_image_to_base64(img_path):
    try:
        # Normalize the path to use lowercase 'images/'
        normalized_path = img_path.replace('Images/', 'images/').replace('IMAGES/', 'images/')
        
        # If the path starts with 'images/', use it as is relative to the workspace root
        if normalized_path.lower().startswith('images/'):
            full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', normalized_path))
        else:
            # Otherwise, assume it's just a filename and look in the images directory
            full_path = os.path.join(IMAGES_DIR, normalized_path)
            
        with Image.open(full_path) as img:
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except (FileNotFoundError, IOError):
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
    session_id = str(uuid.uuid4())
    try:
        if not os.path.exists(TAG_FILE):
            sample_data = {'filename': ['images/animal1.jpeg', 'images/animal2.jpeg', 'images/vehicle1.jpeg'],
                           'tags': ['animal|pet|cat', 'animal|pet|dog', 'vehicle|car']}
            pd.DataFrame(sample_data).to_csv(TAG_FILE, index=False)
        image_tags_df = load_image_tags(TAG_FILE)
        if image_tags_df.empty:
            return jsonify({"error": "empty_file", "message": "No valid data found in CSV file."})
    except FileNotFoundError:
        return jsonify({"error": "file_not_found", "message": "Image tag file not found."})

    if request.method == 'POST':
        # Add time-based seed before any random operations
        random.seed(int(time.time() * 1000))
        
        # Parse form data
        antecedent_data = json.loads(request.form.get('antecedent_data', '[]'))
        behavior_data = json.loads(request.form.get('behavior_data', '{}'))
        consequence_data = json.loads(request.form.get('consequence_data', '{}'))

        # **Update Default Grid Values Here**
        grid_rows = int(request.form.get('grid_rows', 1))  # Changed default from 2 to 1
        grid_cols = int(request.form.get('grid_cols', 3))  # Changed default from 2 to 3
        image_size = int(request.form.get('image_size', 250))

        selected_tags = [item['tag'] for item in antecedent_data if item['tag']]
        visible_tags = [item['tag'] for item in antecedent_data if item['tag'] and item['visible']]
        action_type = behavior_data.get('action_type', 'click')

        # Parse Consequence Data
        enable_prompting = consequence_data.get('enable_prompting', False)
        prompt_type = consequence_data.get('prompt_type', '') if enable_prompting else ''
        use_prompt_delay = consequence_data.get('use_prompt_delay', False) if enable_prompting else False
        prompt_delay = float(consequence_data.get('prompt_delay', 0)) if use_prompt_delay else 0
        fade_duration = float(consequence_data.get('fade_duration', 1)) if consequence_data.get('fade_duration') else 1

        # Corrected fade_opacity calculation
        fade_percentage_input = int(consequence_data.get('fade_percentage', 40)) / 100  # Convert to decimal
        fade_opacity = 1 - fade_percentage_input  # Invert to get opacity

        highlight_color = consequence_data.get('highlight_color', '#28a745')  # Default to green

        # Reinforcement Option
        enable_reinforcement = consequence_data.get('enable_reinforcement', False)
        enable_dance_animation = consequence_data.get('enable_dance_animation', False)

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
                image_data_list.append({
                    'img_base64': img_base64,
                    'img_tags': json.dumps(list(img_tags)),
                    'img_path': img_path,
                    'data_correct': data_correct,
                    'action_type': action_type
                })

        # No sample image data needed since MTS is removed
        sample_image_data = None

        # Store prompt settings to pass to the frontend
        prompt_settings = {
            'enable_prompting': enable_prompting,
            'use_prompt_delay': use_prompt_delay,
            'prompt_delay': prompt_delay,
            'prompt_type': prompt_type,
            'fade_duration': fade_duration,
            'fade_opacity': fade_opacity,  # Use inverted fade_percentage
            'highlight_color': highlight_color,
            'enable_reinforcement': enable_reinforcement,
            'enable_dance_animation': enable_dance_animation,
            'enable_glow': bool(request.form.get('enable_glow'))
        }

        # Render the template with all necessary variables
        return render_template('grid.html', 
                             grid_cols=grid_cols,
                             fade_opacity=fade_opacity,
                             fade_duration=fade_duration,
                             highlight_color=highlight_color,
                             visible_tags=visible_tags,
                             image_data_list=image_data_list,
                             action_type=action_type,
                             prompt_settings=prompt_settings,
                             selected_tags=selected_tags,
                             image_size=image_size,
                             session_id=session_id)

    # Initial Form for User Input
    return render_template('config.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5008, debug=True)
