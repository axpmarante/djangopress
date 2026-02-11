from django.urls import path
from . import views

app_name = 'site_assistant'

urlpatterns = [
    path('', views.AssistantPageView.as_view(), name='assistant'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/confirm/', views.confirm_api, name='confirm_api'),
    path('api/sessions/', views.sessions_api, name='sessions_api'),
    path('api/sessions/<int:session_id>/', views.session_detail_api, name='session_detail_api'),
]
