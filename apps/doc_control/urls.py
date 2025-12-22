from django.urls import path
from . import views

app_name = 'doc_control'

urlpatterns = [
    # Dashboard
    path('', views.document_dashboard, name='dc_dashboard'),
    
    # Document Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    
    # Controlled Documents
    path('documents/', views.document_list, name='document_list'),
    path('documents/create/', views.document_create, name='document_create'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/edit/', views.document_edit, name='document_edit'),
    path('documents/<int:pk>/download/', views.document_download, name='document_download'),
    
    # Version Control
    path('documents/<int:document_pk>/versions/create/', views.version_create, name='version_create'),
    path('documents/<int:document_pk>/versions/', views.version_list, name='version_list'),
    
    # Reviews
    path('reviews/', views.review_list, name='review_list'),
    path('reviews/create/', views.review_create, name='review_create'),
    path('reviews/<int:pk>/', views.review_detail, name='review_detail'),
    path('documents/<int:document_pk>/reviews/create/', views.review_create, name='document_review_create'),
    
    # Approvals
    path('documents/<int:pk>/approve/', views.document_approve, name='document_approve'),
    
    # Distribution
    path('documents/<int:document_pk>/distribute/', views.distribution_create, name='distribution_create'),
    path('distributions/<int:distribution_pk>/acknowledge/', views.document_acknowledge, name='document_acknowledge'),
    
    # Training
    path('training/', views.training_list, name='training_list'),
    path('documents/<int:document_pk>/training/assign/', views.training_assign, name='training_assign'),
    
    # References
    path('documents/<int:document_pk>/references/create/', views.reference_create, name='reference_create'),
    
    # Reports
    path('reports/', views.document_reports, name='reports'),
]


# from django.urls import path
# from . import views

# app_name = 'document'

# urlpatterns = [
#     path("dashboard/", views.document_dashboard, name="document_dashboard"),

#     # catrgory


#     # path("dashboard/", views.dashboard_view, name="document_control_dashboard"),

#     # path('categories/', views.category_list, name='category_list'),
#     # path('categories/create/', views.category_create, name='category_create'),
#     # path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
#     # path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'), # AJAX or Javascript handles the call -- no page

#     # path('documents/', views.document_list, name='document_list'),
#     # path('documents/create/', views.document_create, name='document_create'),
#     # path('documents/<int:pk>/edit/', views.document_edit, name='document_edit'),
#     # path('documents/<int:pk>/', views.document_detail, name='document_detail'),
#     # path('documents/<int:pk>/delete/', views.document_delete, name='document_delete'), # AJAX or Javascript handles the call -- no page

#     # path('versions/upload/<int:doc_id>/', views.version_upload, name='version_upload'),
#     # path('versions/<int:pk>/', views.version_detail, name='version_detail'),
#     # path('versions/<int:pk>/start-review/', views.start_review, name='version_start_review'), # AJAX or Javascript handles the call -- no page
#     # path('versions/<int:pk>/approve/', views.approve_version, name='version_approve'),
#     # path('versions/<int:pk>/acknowledge/', views.acknowledge_training, name='version_acknowledge'), # AJAX or Javascript handles the call -- no page
# ]

