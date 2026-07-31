document.addEventListener('DOMContentLoaded', function() {
    // ── Test picker ──────────────────────────────────────────────
    // With a registered participant, show the picker so they choose
    // which test to play; otherwise show the registration form.
    const RESULT_KEYS = {
        'go_no_go.html':     'goNoGo',
        'pvt.html':          'pvt',
        'trail_making.html': 'trailMaking',
        'dual_n_back.html':  'dualNBack'
    };

    function showTestPicker() {
        document.getElementById('registrationSection').style.display = 'none';
        document.getElementById('testPickerSection').style.display = 'block';

        const user      = JSON.parse(sessionStorage.getItem('currentUser') || 'null');
        const completed = JSON.parse(sessionStorage.getItem('completedTests')) || [];

        document.querySelectorAll('.test-pick-card').forEach(card => {
            const test = card.dataset.test;
            const done = completed.includes(test) || !!(user && user.results && user.results[RESULT_KEYS[test]]);
            const badge = card.querySelector('.tp-status');
            if (done) {
                card.classList.add('tp-done');
                badge.textContent = '✓ Completed — click to replay';
            } else {
                badge.textContent = 'Not played yet';
            }
        });

        if (user && user.name) {
            document.getElementById('pickerGreeting').textContent =
                `${user.name}, pick any test to play — results save automatically after each one.`;
        }
    }

    document.getElementById('finishBtn').addEventListener('click', () => {
        window.location.href = 'completion.html';
    });

    document.getElementById('newParticipantBtn').addEventListener('click', () => {
        sessionStorage.removeItem('currentUser');
        sessionStorage.removeItem('completedTests');
        sessionStorage.removeItem('dataSaved');
        document.getElementById('testPickerSection').style.display = 'none';
        document.getElementById('registrationSection').style.display = 'block';
    });

    // Guest mode: skip registration and go straight to the picker.
    // Guest rows are named "Guest" so they are easy to filter out of exports.
    document.getElementById('guestBtn').addEventListener('click', () => {
        const guest = {
            id: 'guest-' + Date.now().toString(),
            name: 'Guest', email: '', age: null, sex: '',
            adhdStatus: '', consent: false,
            stateAssessment: { sleepiness: null, feeling: null, mood: null, timestamp: new Date().toISOString() },
            results: { goNoGo: null, pvt: null, trailMaking: null, dualNBack: null },
            testStartTime: new Date().toISOString(),
            completedTests: []
        };
        const allUsers = JSON.parse(localStorage.getItem('users')) || [];
        allUsers.push(guest);
        localStorage.setItem('users', JSON.stringify(allUsers));
        sessionStorage.setItem('currentUser', JSON.stringify(guest));
        showTestPicker();
    });

    if (sessionStorage.getItem('currentUser')) {
        showTestPicker();
        return;
    }

    // Initialize users array
    let users = JSON.parse(localStorage.getItem('users')) || [];
    
    // Update range value displays
    const updateRangeValue = (sliderId, valueId) => {
        const slider = document.getElementById(sliderId);
        const value = document.getElementById(valueId);
        if (slider && value) {
            slider.addEventListener('input', function() {
                value.textContent = this.value;
            });
        }
    };
    
    updateRangeValue('sleepiness', 'sleepinessValue');
    updateRangeValue('feeling', 'feelingValue');
    updateRangeValue('mood', 'moodValue');

    // Handle form submission
    const userInfoForm = document.getElementById('userInfoForm');
    if (userInfoForm) {
        userInfoForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form values
            const formData = {
                name:        document.getElementById('userName').value.trim(),
                email:       document.getElementById('userEmail').value.trim(),
                age:         parseInt(document.getElementById('userAge').value),
                sex:         document.querySelector('input[name="sex"]:checked')?.value,
                // ADHD label: collected for supervised classification
                adhdStatus:  document.querySelector('input[name="adhdStatus"]:checked')?.value || '',
                consent:     document.getElementById('consent').checked,
                sleepiness:  parseInt(document.getElementById('sleepiness').value),
                feeling:     parseInt(document.getElementById('feeling').value),
                mood:        parseInt(document.getElementById('mood').value)
            };
            
            // Validate form
            if (!formData.name || !formData.email || isNaN(formData.age) || !formData.sex || !formData.consent) {
                showError('Please fill all required fields');
                return;
            }
            
            if (formData.age < 18) {
                showError('You must be at least 18 years old to participate');
                return;
            }
            
            // Create user object
            const user = {
                id: Date.now().toString(),
                ...formData,
                stateAssessment: {
                    sleepiness: formData.sleepiness,
                    feeling: formData.feeling,
                    mood: formData.mood,
                    timestamp: new Date().toISOString()
                },
                results: {
                    
                    goNoGo: null,
                    pvt: null,
                    trailMaking: null,
                    dualNBack: null
                },
                testStartTime: new Date().toISOString(),
                completedTests: []
            };
            
            // Save to storage
            users.push(user);
            localStorage.setItem('users', JSON.stringify(users));
            sessionStorage.setItem('currentUser', JSON.stringify(user));

            // Let the participant choose which test to play
            showTestPicker();
        });
    }
    
    // Error handling
    function showError(message) {
        const errorElement = document.createElement('div');
        errorElement.className = 'error-message';
        errorElement.textContent = message;
        errorElement.style.cssText = `
            color: #dc3545;
            margin: 15px 0;
            padding: 12px;
            background-color: #f8d7da;
            border-radius: 6px;
            border: 1px solid #f5c6cb;
            text-align: center;
            font-weight: 500;
        `;
        
        const form = document.getElementById('userInfoForm');
        if (form) {
            const submitButton = form.querySelector('button[type="submit"]');
            form.insertBefore(errorElement, submitButton);
            
            setTimeout(() => {
                errorElement.style.opacity = '0';
                setTimeout(() => errorElement.remove(), 300);
            }, 5000);
        }
    }
});