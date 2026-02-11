from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # Conversation list and detail views
    path('', views.ConversationListView.as_view(), name='list'),
    path('new/', views.NewConversationView.as_view(), name='new'),
    path('archived/', views.ArchivedConversationsView.as_view(), name='archived'),
    path('<int:pk>/', views.ConversationDetailView.as_view(), name='detail'),

    # API endpoints for AJAX operations
    path('api/conversations/<int:pk>/send/', views.SendMessageAPI.as_view(), name='api_send'),
    path('api/conversations/<int:pk>/messages/', views.MessagesAPI.as_view(), name='api_messages'),
    path('api/conversations/<int:pk>/confirm/', views.ConfirmActionAPI.as_view(), name='api_confirm'),
    path('api/conversations/<int:pk>/update/', views.UpdateConversationAPI.as_view(), name='api_update'),
    path('api/conversations/<int:pk>/archive/', views.ArchiveConversationAPI.as_view(), name='api_archive'),
    path('api/conversations/<int:pk>/unarchive/', views.UnarchiveConversationAPI.as_view(), name='api_unarchive'),
    path('api/conversations/<int:pk>/delete/', views.DeleteConversationAPI.as_view(), name='api_delete'),
]
