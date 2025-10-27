onboarding of vendors 
Click on join --- Fill forms, which the admin will receive,







<!-- {% extends "base.html" %}
{% block content %}
<div class="onboard-container">
    <div class="onboard-card">
        <h2>Welcome Back</h2>
        <p class="subtitle">Sign in to continue</p>

        {% if form.errors %}
        <div class="alert error">Invalid login credentials. Please try again.</div>
        {% endif %}

        <form method="POST">
            {% csrf_token %}
            <div class="form-group">
                <label for="id_username">Email Address</label>
                {{ form.username }}
            </div>
            <div class="form-group">
                <label for="id_password">Password</label>
                {{ form.password }}
            </div>

            <button type="submit" class="btn-primary">Login</button>
        </form>
        <p class="subtitle" style="margin-top:1rem;">
            <a href="#" style="color:#a80e09; font-weight:500;">Forgot password?</a>
        </p>

        <p class="subtitle">
            Don't have an account?
            <a href="{% url 'register' %}" style="color:#a80e09; font-weight:500;">Sign up</a>
        </p>
    </div>
</div>
{% endblock %} -->








Departments:
1. Hematology & Immunology 
2. Chemical Pathology 
3. Medical Microbiology 
4. Histopathology 
5. Cytology
6. Molecular Diagnostics 
7. Radiology
    And there are different tests under each category. From the front end, patient details with clinical & sample information and specific test requests are logged in.


Dashboard
patients -
Samples
Results
Equipment
Analytics
CRM
settings