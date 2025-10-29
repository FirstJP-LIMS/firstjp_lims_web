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



"""
Departments:
1. Hematology & Immunology 
2. Chemical Pathology 
3. Medical Microbiology 
4. Histopathology 
5. Cytology
6. Molecular Diagnostics 
7. Radiology
    And there are different tests under each category. From the front end, patient details with clinical & sample information and specific test requests are logged in.
    If you have the know of how lims work, can you break things down, for execution...

Department and Test type to be controlled by the platform admin. i.e the LIMS, has all department available to all tenants..
Vendor, controls, their lab assistants, patients, samples, test requests and results.


Ask Scientist - If Each tenant can choose which department and test types they want to enable for their lab, or all tenants have access to all departments and test types by default.

# ---------------------
# Tenant-Scoped Models (Vendor Managed)
# Patient	TENANT	Patient records specific to the vendor/lab.
# TestRequest	TENANT	The patient's order for a list of tests.
# Sample	TENANT	The physical specimen received by the vendor/lab.
# TestAssignment	TENANT	Tracks the execution of a GlobalTest within this vendor's workflow.
# Result	TENANT	The final measured value for a TestAssignment.
# Equipment	TENANT	Tracks the vendor's specific lab instruments.
# ---------------------

"""