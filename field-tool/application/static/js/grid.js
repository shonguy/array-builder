function initializeGrid(actionType, promptSettings) {
    const {
        enable_prompting,
        use_prompt_delay,
        prompt_delay,
        prompt_type,
        fade_duration,
        fade_opacity,
        highlight_color,
        enable_reinforcement,
        enable_dance_animation
    } = promptSettings;

    let interactionData = [];

    function handleAction(element, action, imgPath, isCorrect, promptUsed) {
        const timeTaken = Date.now() - startTime;
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
            element.addEventListener('animationend', function() {
                element.classList.remove('dance-animation');
                element.classList.add('correct');
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
        return tags.find(tag => selectedTags.includes(tag)) || 'Unknown';
    }

    function promptByExclusion() {
        document.querySelectorAll('.grid-image-container[data-correct="false"]').forEach(container => {
            container.classList.add('prompt-fade');
        });
    }

    function promptByHighlighting() {
        document.querySelectorAll('.grid-image-container[data-correct="true"]').forEach(container => {
            container.style.color = promptSettings.highlight_color;
            container.style.borderColor = promptSettings.highlight_color;
            container.classList.add('blink-border');
        });
    }

    if (actionType === 'click') {
        document.querySelectorAll('.grid-image-container').forEach(container => {
            container.addEventListener('click', function() {
                handleAction(this, 'click', this.dataset.path, this.dataset.correct === 'true', prompt_type || 'None');
            });
        });
    } else if (actionType === 'click_and_drag') {
        // Bidirectional Drag and Drop Setup
        const draggableElements = document.querySelectorAll('.grid-image-container, .target-drop-zone');

        draggableElements.forEach(element => {
            element.setAttribute('draggable', 'true');

            element.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', null); // For Firefox compatibility
                element.classList.add('dragging');
            });

            element.addEventListener('dragend', () => {
                element.classList.remove('dragging');
            });
        });

        const droppableElements = document.querySelectorAll('.grid-image-container, .target-drop-zone');

        droppableElements.forEach(element => {
            element.addEventListener('dragover', e => {
                e.preventDefault();
            });

            element.addEventListener('drop', e => {
                e.preventDefault();
                const draggingElement = document.querySelector('.dragging');

                if (draggingElement && draggingElement !== element) {
                    const sourceTags = JSON.parse(draggingElement.dataset.tags || '[]');
                    const targetTags = JSON.parse(element.dataset.tags || '[]');

                    // Determine if the match is correct
                    const isCorrect = sourceTags.some(tag => targetTags.includes(tag));

                    // Get image path (if any)
                    let imgPath = draggingElement.dataset.path || element.dataset.path || 'N/A';

                    handleAction(element, 'bidirectional_drag', imgPath, isCorrect, prompt_type || 'None');

                    if (enable_reinforcement) {
                        updateVisualFeedback(draggingElement, isCorrect);
                        updateVisualFeedback(element, isCorrect);
                    }
                }
            });
        });
    } else if (actionType === 'manual_data_entry') {
        const correctBtn = document.querySelector('#manualEntryButtons .correct-btn');
        const incorrectBtn = document.querySelector('#manualEntryButtons .incorrect-btn');

        correctBtn.addEventListener('click', function() {
            handleAction(null, 'manual_entry', null, true, prompt_type || 'None');
        });

        incorrectBtn.addEventListener('click', function() {
            handleAction(null, 'manual_entry', null, false, prompt_type || 'None');
        });
    }

    if (enable_prompting && use_prompt_delay && prompt_delay > 0) {
        setTimeout(() => {
            applyPrompt();
        }, prompt_delay * 1000);
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

    // Add debug logging for End Trial button
    const endTrialBtn = document.getElementById('endTrialBtn');
    console.log('End Trial button found:', endTrialBtn);
    
    endTrialBtn.addEventListener('click', function() {
        console.log('End Trial button clicked');
        showSummary();
        console.log('Summary shown, preparing to redirect...');
        // Add a slight delay to ensure summary is shown before redirecting
        setTimeout(() => {
            console.log('Redirecting to home...');
            window.location.href = '/';
        }, 2000); // 2 second delay to show summary before redirect
    });

    // Set up summary modal button listeners once
    document.getElementById('downloadDataBtn').addEventListener('click', function() {
        window.location.href = '/download_data/' + sessionId;
    });
    
    document.getElementById('returnToConfigBtn').addEventListener('click', function() {
        window.location.href = '/';
    });

    function showSummary() {
        console.log('Showing summary...');
        const totalTrials = interactionData.length;
        const correctResponses = interactionData.filter(d => d.correct === 'Correct').length;
        const incorrectResponses = totalTrials - correctResponses;
        const accuracy = ((correctResponses / totalTrials) * 100).toFixed(2);

        console.log('Summary data:', { totalTrials, correctResponses, incorrectResponses, accuracy });

        document.getElementById('summaryText').innerHTML = `
            Total Trials: ${totalTrials}<br>
            Correct Responses: ${correctResponses}<br>
            Incorrect Responses: ${incorrectResponses}<br>
            Accuracy: ${accuracy}%
        `;
        document.getElementById('summaryModal').style.display = 'flex';
        console.log('Summary modal displayed');
    }

    window.addEventListener('click', function(event) {
        if (event.target == document.getElementById('summaryModal')) {
            document.getElementById('summaryModal').style.display = 'none';
        }
    });
}

// Initialize the grid when the script loads
console.log('Initializing grid with:', { actionType, promptSettings });
initializeGrid(actionType, promptSettings); 