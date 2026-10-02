"""
URL configuration for the editor.
"""
from django.urls import path
from . import api_views, chat_views, component_views, unsplash_views

app_name = 'editor_v2'

urlpatterns = [
    # Page editing API endpoints
    path('api/update-page-content/', api_views.update_page_content, name='api_update_page_content'),
    path('api/update-page-classes/', api_views.update_page_element_classes, name='api_update_page_classes'),
    path('api/design-tokens/', api_views.design_tokens, name='api_design_tokens'),
    path('api/restyle-similar/', api_views.restyle_similar, name='api_restyle_similar'),
    path('api/update-page-attribute/', api_views.update_page_element_attribute, name='api_update_page_attribute'),
    path('api/update-section-video/', api_views.update_section_video, name='api_update_section_video'),
    path('api/media-library/', api_views.get_media_library, name='api_media_library'),

    # Image management endpoints
    path('api/images/', api_views.get_images, name='get_images'),
    path('api/images/upload/', api_views.upload_image, name='upload_image'),
    path('api/images/unsplash-search/', unsplash_views.unsplash_search, name='api_unsplash_search'),
    path('api/images/unsplash-import/', unsplash_views.unsplash_import, name='api_unsplash_import'),

    # AI section refinement endpoints
    path('api/refine-section/', api_views.refine_section, name='api_refine_section'),
    path('api/save-ai-section/', api_views.save_ai_section, name='api_save_ai_section'),

    # AI element refinement endpoints
    path('api/refine-element/', api_views.refine_element, name='api_refine_element'),
    path('api/save-ai-element/', api_views.save_ai_element, name='api_save_ai_element'),

    # AI multi-option refinement endpoints
    path('api/refine-multi/', api_views.refine_multi, name='api_refine_multi'),
    path('api/refine-multi/stream/', api_views.refine_multi_stream, name='api_refine_multi_stream'),
    path('api/apply-option/', api_views.apply_option, name='api_apply_option'),
    path('api/chat/stream/', chat_views.chat_stream, name='api_chat_stream'),
    path('api/chat/cancel/', chat_views.chat_cancel, name='api_chat_cancel'),
    path('api/chat/context/', chat_views.chat_context, name='api_chat_context'),

    # Remove section/element endpoints
    path('api/remove-section/', api_views.remove_section, name='api_remove_section'),
    path('api/remove-element/', api_views.remove_element, name='api_remove_element'),

    # Structural verbs (no LLM)
    path('api/duplicate-element/', api_views.duplicate_element, name='api_duplicate_element'),
    path('api/move-element/', api_views.move_element, name='api_move_element'),
    path('api/insert-element/', api_views.insert_element, name='api_insert_element'),
    path('api/duplicate-section/', api_views.duplicate_section, name='api_duplicate_section'),
    path('api/move-section/', api_views.move_section, name='api_move_section'),
    path('api/retag-element/', api_views.retag_element, name='api_retag_element'),
    path('api/link-targets/', api_views.link_targets, name='api_link_targets'),
    path('api/page-copies/', api_views.page_copies, name='api_page_copies'),
    path('api/component/', component_views.component_op, name='api_component_op'),

    # AI full-page refinement endpoints
    path('api/refine-page/', api_views.refine_page, name='api_refine_page'),
    path('api/refine-page/stream/', api_views.refine_page_stream, name='api_refine_page_stream'),
    path('api/save-ai-page/', api_views.save_ai_page, name='api_save_ai_page'),

    # Session history endpoint
    path('api/session/<int:page_id>/', api_views.get_editor_session, name='api_get_session'),

    # Version navigation endpoints
    path('api/versions/<int:page_id>/', api_views.list_page_versions, name='api_list_versions'),
    path('api/versions/<int:page_id>/<int:version_number>/', api_views.get_page_version, name='api_get_version'),

    # Undo / redo / checkpoints
    path('api/checkpoint/', api_views.create_checkpoint, name='api_checkpoint'),
    path('api/history/<int:page_id>/', api_views.history_state, name='api_history'),
    path('api/undo/', api_views.undo, name='api_undo'),
    path('api/redo/', api_views.redo, name='api_redo'),
    path('api/restore-version/', api_views.restore_version, name='api_restore_version'),
]
