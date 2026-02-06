"""
URL configuration for builder app.
"""
from django.urls import path
from . import api_views, views

app_name = 'builder'

urlpatterns = [
    # Page-based API endpoints
    path('api/update-page-content/', api_views.update_page_content, name='api_update_page_content'),
    path('api/update-page-classes/', api_views.update_page_element_classes, name='api_update_page_classes'),
    path('api/update-page-attribute/', api_views.update_page_element_attribute, name='api_update_page_attribute'),
    path('api/media-library/', api_views.get_media_library, name='api_media_library'),

    # Image management endpoints
    path('api/images/', views.get_images, name='get_images'),
    path('api/images/upload/', views.upload_image, name='upload_image'),
]
