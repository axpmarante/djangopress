"""
URL configuration for the editor.
"""
from django.urls import path
from . import api_views

app_name = 'editor_v2'

urlpatterns = [
    # Page editing API endpoints
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

    # AI element refinement endpoints
    path('api/refine-element/', api_views.refine_element, name='api_refine_element'),
    path('api/save-ai-element/', api_views.save_ai_element, name='api_save_ai_element'),

    # AI multi-option refinement endpoints
    path('api/refine-multi/', api_views.refine_multi, name='api_refine_multi'),
    path('api/apply-option/', api_views.apply_option, name='api_apply_option'),

    # Remove section/element endpoints
    path('api/remove-section/', api_views.remove_section, name='api_remove_section'),
    path('api/remove-element/', api_views.remove_element, name='api_remove_element'),

    # AI full-page refinement endpoints
    path('api/refine-page/', api_views.refine_page, name='api_refine_page'),
    path('api/save-ai-page/', api_views.save_ai_page, name='api_save_ai_page'),

    # Session history endpoint
    path('api/session/<int:page_id>/', api_views.get_editor_session, name='api_get_session'),

    # Version navigation endpoints
    path('api/versions/<int:page_id>/', api_views.list_page_versions, name='api_list_versions'),
    path('api/versions/<int:page_id>/<int:version_number>/', api_views.get_page_version, name='api_get_version'),
]
