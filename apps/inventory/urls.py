from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.inventory_dashboard, name='dashboard'),
    
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/', views.category_detail, name='category_detail'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('categories/<int:pk>/export/', views.category_items_export, name='category_items_export'),

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
    path('lots/<int:pk>/delete/', views.stock_lot_delete, name='lot_delete'),
    path('lots/<int:pk>/mark-expired/', views.stock_lot_mark_expired, name='lot_mark_expired'),
    # Stock Adjustments
    path('lots/<int:pk>/quick-adjust/', views.stock_lot_quick_adjust, name='lot_quick_adjust'),

    # Reagent Usage
    path('usage/add/', views.reagent_usage_create, name='usage_create'),
    path('usage/<int:pk>/delete/', views.reagent_usage_delete, name='usage_delete'),

    # Stock Adjustments
    # path('adjustments/add/', views.stock_adjustment_create, name='adjustment_create'),
    
    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='po_list'),
    path('purchase-orders/add/', views.purchase_order_create, name='po_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='po_detail'),
    path('purchase-orders/<int:pk>/edit/', views.purchase_order_update, name='po_update'),
    path('purchase-orders/<int:pk>/delete/', views.purchase_order_delete, name='po_delete'),
    

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
