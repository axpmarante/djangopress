"""
Executive Coach URL Configuration
"""

from django.urls import path
from . import views

app_name = 'coach'

urlpatterns = [
    path('', views.CoachChatView.as_view(), name='chat'),
    path('send/', views.CoachSendMessageView.as_view(), name='send'),
    path('new/', views.CoachNewConversationView.as_view(), name='new'),
    path('messages/', views.CoachMessagesView.as_view(), name='messages'),
]
