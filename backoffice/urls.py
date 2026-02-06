from django.urls import path
from django.contrib.auth import views as auth_views
from . import views, api_views
from news import views as news_views

app_name = 'backoffice'

urlpatterns = [
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='backoffice/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),

    # API Endpoints
    path('api/update-site-settings/', api_views.update_site_settings, name='api_update_site_settings'),
    path('api/update-languages/', api_views.update_languages, name='api_update_languages'),
    path('api/media-library/', api_views.get_media_library, name='api_media_library'),
    path('api/upload-images/', api_views.upload_images, name='api_upload_images'),
    path('api/page-content/<int:page_id>/', api_views.get_page_content, name='api_page_content'),

    # Media Management
    path('media/', views.MediaView.as_view(), name='media'),
    path('media/upload/', views.MediaUploadView.as_view(), name='media_upload'),
    path('media/bulk-upload/', views.MediaBulkUploadView.as_view(), name='media_bulk_upload'),

    # News Management
    path('news/', news_views.NewsListView.as_view(), name='news_list'),
    path('news/create/', news_views.NewsCreateView.as_view(), name='news_create'),
    path('news/<int:pk>/edit/', news_views.NewsUpdateView.as_view(), name='news_edit'),
    path('news/<int:pk>/delete/', news_views.NewsDeleteView.as_view(), name='news_delete'),
    path('news/<int:pk>/gallery/', news_views.NewsGalleryView.as_view(), name='news_gallery'),

    # Pages Management
    path('pages/', views.PagesView.as_view(), name='pages'),
    path('page/<int:page_id>/edit/', views.PageEditView.as_view(), name='page_edit'),

    # Settings
    path('settings/', views.SettingsView.as_view(), name='settings'),
    path('settings/header/', views.HeaderEditView.as_view(), name='header_edit'),
    path('settings/footer/', views.FooterEditView.as_view(), name='footer_edit'),

    # AI Content Studio
    path('ai/', views.AIManagementView.as_view(), name='ai_management'),
    path('ai/generate/page/', views.AIGeneratePageView.as_view(), name='ai_generate_page'),
    path('ai/bulk/pages/', views.AIBulkPagesView.as_view(), name='ai_bulk_pages'),
    path('ai/refine/page/', views.AIRefinePageView.as_view(), name='ai_refine_page'),
    path('ai/refine/page/<str:page_slug>/', views.AIRefinePageView.as_view(), name='ai_refine_page_with_slug'),
    path('ai/components/', views.AIComponentsView.as_view(), name='ai_components'),

    # Version Management
    path('version/page/<int:version_id>/restore/', views.restore_page_version, name='restore_page_version'),
]
