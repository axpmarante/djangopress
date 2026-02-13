"""
URL configuration for editor v2.
Reuses the same API views from editor app — no API duplication.
"""
from django.urls import path
from editor import api_views

app_name = 'editor_v2'

urlpatterns = [
    # Page editing API endpoints (shared with editor v1)
    path('api/update-page-content/', api_views.update_page_content, name='api_update_page_content'),
    path('api/update-page-classes/', api_views.update_page_element_classes, name='api_update_page_classes'),
    path('api/update-page-attribute/', api_views.update_page_element_attribute, name='api_update_page_attribute'),
    path('api/update-section-video/', api_views.update_section_video, name='api_update_section_video'),
    path('api/media-library/', api_views.get_media_library, name='api_media_library'),

    # Image management endpoints
    path('api/images/', api_views.get_images, name='get_images'),
    path('api/images/upload/', api_views.upload_image, name='upload_image'),

    # AI section refinement endpoints
    path('api/refine-section/', api_views.refine_section, name='api_refine_section'),
    path('api/save-ai-section/', api_views.save_ai_section, name='api_save_ai_section'),
]
