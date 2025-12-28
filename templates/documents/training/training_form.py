{% extends 'laboratory/assets/base.html' %}
{% load static %}

{% block title %}{{ title }}{% endblock %}

{% block content %}
<div class="container">
    <!-- Header -->
    <div class="row align-items-center mb-5">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h2 class="h3 mb-2" style="color: var(--primary-color);">
                        <i class="fas fa-graduation-cap me-2"></i>
                        {{ title }}
                    </h2>
                    <p class="text-muted mb-0">
                        For document: <strong>{{ document.document_number }} - {{ document.title|truncatechars:50 }}</strong>
                    </p>
                </div>
                <div>
                    <a href="{% url 'documents:document_detail' document.pk %}" class="btn btn-outline-secondary">
                        <i class="fas fa-arrow-left me-1"></i> Back
                    </a>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <div class="row">
        <div class="col-lg-8">
            <!-- Form Section -->
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-light border-0">
                    <h5 class="mb-0">
                        <i class="fas fa-user-graduate me-2"></i>Training Assignment
                    </h5>
                </div>
                <div class="card-body">
                    <form method="post" id="trainingForm">
                        {% csrf_token %}
                        
                        <!-- Form Errors -->
                        {% if form.non_field_errors %}
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            {{ form.non_field_errors }}
                        </div>
                        {% endif %}

                        <!-- Document Information -->
                        <div class="card mb-4 border">
                            <div class="card-header bg-light border-bottom">
                                <h6 class="mb-0">
                                    <i class="fas fa-file-alt me-2"></i>Training Document
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="row g-3">
                                    <div class="col-md-6">
                                        <table class="table table-sm table-borderless mb-0">
                                            <tbody>
                                                <tr>
                                                    <th width="40%" class="text-muted">Document:</th>
                                                    <td>{{ document.document_number }}</td>
                                                </tr>
                                                <tr>
                                                    <th class="text-muted">Title:</th>
                                                    <td>{{ document.title|truncatechars:40 }}</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                    <div class="col-md-6">
                                        <table class="table table-sm table-borderless mb-0">
                                            <tbody>
                                                <tr>
                                                    <th width="40%" class="text-muted">Version:</th>
                                                    <td>
                                                        <span class="badge bg-info">v{{ document.version }}</span>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <th class="text-muted">Training Required:</th>
                                                    <td>
                                                        {% if document.requires_training %}
                                                        <i class="fas fa-check-circle text-success"></i> Yes
                                                        {% else %}
                                                        <i class="fas fa-times-circle text-danger"></i> No
                                                        {% endif %}
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Training Type -->
                        <div class="card mb-4 border">
                            <div class="card-header bg-light border-bottom">
                                <h6 class="mb-0">
                                    <i class="fas fa-tasks me-2"></i>Training Details
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="row g-3">
                                    <div class="col-md-12">
                                        <label for="{{ form.training_type.id_for_label }}" class="form-label fw-semibold">
                                            <i class="fas fa-clipboard-list me-1"></i> Training Type *
                                        </label>
                                        <div class="input-group">
                                            {{ form.training_type }}
                                            <span class="input-group-text bg-light">
                                                <i class="fas fa-graduation-cap text-muted"></i>
                                            </span>
                                        </div>
                                        {% if form.training_type.errors %}
                                        <div class="text-danger small mt-1">
                                            {% for error in form.training_type.errors %}
                                            <i class="fas fa-exclamation-circle me-1"></i>{{ error }}
                                            {% endfor %}
                                        </div>
                                        {% endif %}
                                        <div class="form-text">
                                            <strong>Initial:</strong> First-time training on this document<br>
                                            <strong>Refresher:</strong> Periodic refresher training<br>
                                            <strong>Update:</strong> Training on document updates
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Trainee Selection -->
                        <div class="card mb-4 border">
                            <div class="card-header bg-light border-bottom">
                                <h6 class="mb-0">
                                    <i class="fas fa-users me-2"></i>Select Trainees
                                    <div class="float-end">
                                        <button type="button" class="btn btn-sm btn-outline-primary" id="selectAllBtn">
                                            <i class="fas fa-check-square me-1"></i>Select All
                                        </button>
                                        <button type="button" class="btn btn-sm btn-outline-secondary" id="deselectAllBtn">
                                            <i class="fas fa-square me-1"></i>Clear All
                                        </button>
                                    </div>
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="row g-3">
                                    <div class="col-md-12">
                                        <label class="form-label fw-semibold">
                                            <i class="fas fa-user-check me-1"></i> Trainees *
                                        </label>
                                        
                                        <div class="trainee-list" style="max-height: 300px; overflow-y: auto;">
                                            {% for choice in form.trainees %}
                                            <div class="form-check mb-2">
                                                {{ choice.tag }}
                                                <label class="form-check-label" for="{{ choice.id_for_label }}">
                                                    {{ choice.choice_label }}
                                                </label>
                                            </div>
                                            {% endfor %}
                                        </div>
                                        
                                        {% if form.trainees.errors %}
                                        <div class="text-danger small mt-1">
                                            {% for error in form.trainees.errors %}
                                            <i class="fas fa-exclamation-circle me-1"></i>{{ error }}
                                            {% endfor %}
                                        </div>
                                        {% endif %}
                                        <div class="form-text">Select one or more users who need training on this document</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Form Actions -->
                        <div class="d-flex justify-content-between mt-5 pt-4 border-top">
                            <a href="{% url 'documents:document_detail' document.pk %}" class="btn btn-outline-secondary">
                                <i class="fas fa-times me-1"></i> Cancel
                            </a>
                            <button type="submit" class="btn btn-primary" id="submitBtn">
                                <i class="fas fa-graduation-cap me-1"></i> Assign Training
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <!-- Sidebar -->
        <div class="col-lg-4">
            <!-- Training Guidelines -->
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-light border-0">
                    <h5 class="mb-0">
                        <i class="fas fa-lightbulb me-2"></i>Training Guidelines (ISO 17025)
                    </h5>
                </div>
                <div class="card-body">
                    <div class="mb-4">
                        <h6 class="text-primary mb-2">
                            <i class="fas fa-calendar-check me-1"></i> When to Assign Training:
                        </h6>
                        <ul class="mb-0 ps-3">
                            <li>New employees joining the team</li>
                            <li>New SOPs or procedures introduced</li>
                            <li>Significant document revisions</li>
                            <li>Periodic refresher requirements</li>
                            <li>After audit findings or deviations</li>
                        </ul>
                    </div>
                    
                    <div class="mb-4">
                        <h6 class="text-primary mb-2">
                            <i class="fas fa-clipboard-check me-1"></i> Training Types:
                        </h6>
                        <div class="d-flex flex-column gap-2">
                            <div class="d-flex align-items-start">
                                <span class="badge bg-primary me-2">Initial</span>
                                <small class="text-muted">First-time training for new documents or staff</small>
                            </div>
                            <div class="d-flex align-items-start">
                                <span class="badge bg-warning me-2">Refresher</span>
                                <small class="text-muted">Periodic retraining (typically annual)</small>
                            </div>
                            <div class="d-flex align-items-start">
                                <span class="badge bg-info me-2">Update</span>
                                <small class="text-muted">Training on specific changes or revisions</small>
                            </div>
                        </div>
                    </div>
                    
                    <div>
                        <h6 class="text-primary mb-2">
                            <i class="fas fa-shield-alt me-1"></i> ISO 17025 Requirements:
                        </h6>
                        <ul class="mb-0 ps-3">
                            <li>Personnel must be competent and trained</li>
                            <li>Training records must be maintained</li>
                            <li>Effectiveness of training should be evaluated</li>
                            <li>Retraining required for significant changes</li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- Quick Stats -->
            <div class="card border-0 shadow-sm">
                <div class="card-header bg-light border-0">
                    <h5 class="mb-0">
                        <i class="fas fa-chart-bar me-2"></i>Training Overview
                    </h5>
                </div>
                <div class="card-body">
                    <table class="table table-sm table-borderless mb-0">
                        <tbody>
                            <tr>
                                <th width="40%" class="text-muted">Document:</th>
                                <td>{{ document.document_number }}</td>
                            </tr>
                            <tr>
                                <th class="text-muted">Category:</th>
                                <td>{{ document.category.name }}</td>
                            </tr>
                            <tr>
                                <th class="text-muted">Training Required:</th>
                                <td>
                                    {% if document.requires_training %}
                                    <span class="badge bg-success">Yes</span>
                                    {% else %}
                                    <span class="badge bg-secondary">No</span>
                                    {% endif %}
                                </td>
                            </tr>
                            <tr>
                                <th class="text-muted">Last Training:</th>
                                <td>{{ document.training_records.last.completed_date|date:"Y-m-d"|default:"Never" }}</td>
                            </tr>
                            <tr>
                                <th class="text-muted">Trained Staff:</th>
                                <td>{{ document.training_records.count }}</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <div class="mt-3 pt-3 border-top">
                        <div class="d-grid gap-2">
                            <a href="{% url 'documents:training_list' %}" class="btn btn-outline-primary btn-sm">
                                <i class="fas fa-list me-1"></i>View All Training
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .container {
        max-width: 1200px;
        margin: 0 auto;
    }
    
    .card {
        border-radius: var(--border-radius);
        transition: var(--transition);
        border: 1px solid #e9ecef;
    }
    
    .form-control, .form-select {
        border-radius: var(--border-radius);
        border: 1px solid #ced4da;
        transition: var(--transition);
    }
    
    .form-control:focus, .form-select:focus {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 0.25rem rgba(44, 90, 160, 0.25);
    }
    
    .form-check-input {
        width: 1.2em;
        height: 1.2em;
        margin-top: 0.2em;
    }
    
    .form-check-input:checked {
        background-color: var(--primary-color);
        border-color: var(--primary-color);
    }
    
    .trainee-list {
        border: 1px solid #dee2e6;
        border-radius: var(--border-radius);
        padding: 1rem;
    }
    
    .trainee-list .form-check {
        padding: 0.5rem;
        border-bottom: 1px solid #f8f9fa;
    }
    
    .trainee-list .form-check:last-child {
        border-bottom: none;
    }
    
    .form-check-label {
        cursor: pointer;
        margin-left: 0.5rem;
    }
    
    @media (max-width: 768px) {
        .container {
            padding-left: 15px;
            padding-right: 15px;
        }
        
        .card-body .row > .col-md-6,
        .card-body .row > .col-md-12 {
            margin-bottom: 1rem;
        }
        
        .d-flex.justify-content-between {
            flex-direction: column;
            gap: 1rem;
        }
        
        .d-flex.justify-content-between .btn {
            width: 100%;
        }
        
        .float-end {
            float: none !important;
            margin-top: 0.5rem;
        }
        
        .float-end .btn {
            margin-bottom: 0.5rem;
        }
    }
</style>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        // Select/Deselect all trainees
        const selectAllBtn = document.getElementById('selectAllBtn');
        const deselectAllBtn = document.getElementById('deselectAllBtn');
        const traineeCheckboxes = document.querySelectorAll('input[name="trainees"]');
        
        if (selectAllBtn && deselectAllBtn && traineeCheckboxes.length > 0) {
            selectAllBtn.addEventListener('click', function() {
                traineeCheckboxes.forEach(cb => cb.checked = true);
            });
            
            deselectAllBtn.addEventListener('click', function() {
                traineeCheckboxes.forEach(cb => cb.checked = false);
            });
        }
        
        // Form validation and confirmation
        const trainingForm = document.getElementById('trainingForm');
        const submitBtn = document.getElementById('submitBtn');
        
        if (trainingForm && submitBtn) {
            trainingForm.addEventListener('submit', function(e) {
                e.preventDefault();
                
                const trainingTypeSelect = document.getElementById('{{ form.training_type.auto_id }}');
                const selectedTrainees = Array.from(traineeCheckboxes).filter(cb => cb.checked);
                
                if (!trainingTypeSelect.value) {
                    alert('Please select a training type.');
                    trainingTypeSelect.focus();
                    return;
                }
                
                if (selectedTrainees.length === 0) {
                    alert('Please select at least one trainee.');
                    return;
                }
                
                const trainingTypeText = trainingTypeSelect.options[trainingTypeSelect.selectedIndex].text;
                const traineeCount = selectedTrainees.length;
                
                let message = 'Training Assignment Confirmation:\n\n';
                message += `Document: ${document.document_number} v${document.version}\n`;
                message += `Training Type: ${trainingTypeText}\n`;
                message += `Number of Trainees: ${traineeCount}\n`;
                message += `Trainees: ${selectedTrainees.length === 1 ? '1 user' : selectedTrainees.length + ' users'}\n\n`;
                message += 'Do you want to assign this training?';
                
                if (confirm(message)) {
                    trainingForm.submit();
                }
            });
        }
        
        // Highlight selected trainees
        traineeCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const label = this.closest('.form-check-label');
                if (label) {
                    if (this.checked) {
                        label.classList.add('fw-semibold', 'text-primary');
                    } else {
                        label.classList.remove('fw-semibold', 'text-primary');
                    }
                }
            });
        });
    });
</script>
{% endblock %}
