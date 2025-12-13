from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.inventory_dashboard, name='dashboard'),
    
    # Inventory Items
    path('items/', views.inventory_item_list, name='item_list'),
    path('items/add/', views.inventory_item_create, name='item_create'),
    path('items/<int:pk>/', views.inventory_item_detail, name='item_detail'),
    path('items/<int:pk>/edit/', views.inventory_item_update, name='item_update'),
    path('items/<int:pk>/delete/', views.inventory_item_delete, name='item_delete'),
    
    # Stock Lots
    path('lots/', views.stock_lot_list, name='lot_list'),
    path('lots/add/', views.stock_lot_create, name='lot_create'),
    path('lots/add/<int:item_id>/', views.stock_lot_create, name='lot_create_for_item'),
    path('lots/<int:pk>/', views.stock_lot_detail, name='lot_detail'),
    path('lots/<int:pk>/edit/', views.stock_lot_update, name='lot_update'),
    
    # Reagent Usage
    path('usage/add/', views.reagent_usage_create, name='usage_create'),
    
    # Stock Adjustments
    path('adjustments/add/', views.stock_adjustment_create, name='adjustment_create'),
    
    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='po_list'),
    path('purchase-orders/add/', views.purchase_order_create, name='po_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='po_detail'),
    path('purchase-orders/<int:pk>/edit/', views.purchase_order_update, name='po_update'),
    
    # Storage Management
    path('storage/', views.storage_unit_list, name='storage_unit_list'),
    path('storage/<int:pk>/', views.storage_unit_detail, name='storage_detail'),
    
    # Stored Samples
    path('samples/', views.stored_sample_list, name='sample_list'),
    path('samples/add/', views.stored_sample_create, name='sample_create'),
    path('samples/<int:pk>/retrieve/', views.stored_sample_retrieve, name='sample_retrieve'),
    
    # Reports & Exports
    path('reports/inventory/', views.inventory_report, name='inventory_report'),
    path('export/csv/', views.export_inventory_csv, name='export_csv'),
]
