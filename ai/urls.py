"""
URL Configuration for AI app
"""
from django.urls import path
from . import views

app_name = 'ai'

urlpatterns = [
    # Page generation and refinement
    path('api/generate-page/', views.generate_page_api, name='generate_page'),
    path('api/refine-page-with-html/', views.refine_page_with_html_api, name='refine_page_with_html'),
    path('api/save-page/', views.save_generated_page_api, name='save_page'),

    # Global section refinement (header/footer)
    path('api/refine-header/', views.refine_header_api, name='refine_header'),
    path('api/refine-footer/', views.refine_footer_api, name='refine_footer'),

    # Bulk page analysis
    path('api/analyze-bulk-pages/', views.analyze_bulk_pages_api, name='analyze_bulk_pages'),
]
