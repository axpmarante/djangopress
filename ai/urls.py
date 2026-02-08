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

    # Chat-based refinement
    path('api/chat-refine-page/', views.chat_refine_page_api, name='chat_refine_page'),
    path('api/refinement-session/<int:session_id>/', views.get_refinement_session_api, name='get_refinement_session'),
    path('api/refinement-sessions/<int:page_id>/', views.list_refinement_sessions_api, name='list_refinement_sessions'),

    # Design guide generation
    path('api/generate-design-guide/', views.generate_design_guide_ai_api, name='generate_design_guide_ai'),

    # Image processing
    path('api/analyze-page-images/', views.analyze_page_images_api, name='analyze_page_images'),
    path('api/process-page-images/', views.process_page_images_api, name='process_page_images'),
]
