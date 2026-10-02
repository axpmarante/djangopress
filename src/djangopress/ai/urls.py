"""
URL Configuration for AI app
"""
from django.urls import path
from . import views

app_name = 'ai'

urlpatterns = [
    # Page generation and refinement
    path('api/save-page/', views.save_generated_page_api, name='save_page'),

    # Global section refinement (header/footer)

    # SSE streaming endpoints
    path('api/generate-page/stream/', views.generate_page_stream, name='generate_page_stream'),
    path('api/refine-header/stream/', views.refine_header_stream, name='refine_header_stream'),
    path('api/refine-footer/stream/', views.refine_footer_stream, name='refine_footer_stream'),

    # Bulk page analysis
    path('api/analyze-bulk-pages/', views.analyze_bulk_pages_api, name='analyze_bulk_pages'),

    # Chat-based refinement

    # Design guide generation
    path('api/generate-design-guide/', views.generate_design_guide_ai_api, name='generate_design_guide_ai'),
    path('api/sync-settings-from-guide/', views.sync_settings_from_guide_api, name='sync_settings_from_guide'),

    # Image processing
    path('api/analyze-page-images/', views.analyze_page_images_api, name='analyze_page_images'),
    path('api/process-page-images/', views.process_page_images_api, name='process_page_images'),

    # Bulk translation
    path('api/translate-to-language/', views.translate_to_language_api, name='translate_to_language'),
    path('api/bulk-translate/', views.bulk_translate_api, name='bulk_translate'),

    # Translation propagation (per-page, per-section)

    # Image descriptions
    path('api/describe-images/', views.describe_images_api, name='describe_images'),

    # Unsplash
    path('api/search-unsplash/', views.search_unsplash_api, name='search_unsplash'),

    # Blueprint AI
    path('api/suggest-page-sections/', views.suggest_page_sections_api, name='suggest_page_sections'),
    path('api/fill-section-content/', views.fill_section_content_api, name='fill_section_content'),

    # Prompt tools
    path('api/enhance-prompt/', views.enhance_prompt_api, name='enhance_prompt'),

    # News post generation and refinement
    path('api/generate-news-post/stream/', views.generate_news_post_stream, name='generate_news_post_stream'),
    path('api/save-news-post/', views.save_news_post_api, name='save_news_post'),

    # Design consistency
    path('api/analyze-consistency/stream/', views.analyze_consistency_stream, name='analyze_consistency_stream'),
    path('api/fix-consistency/stream/', views.fix_consistency_stream, name='fix_consistency_stream'),
]
