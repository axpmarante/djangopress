from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Home page (root path)
    path('', views.PageView.as_view(), name='home'),

    # Contact form submission
    path('contact/submit/', views.ContactFormView.as_view(), name='contact_submit'),

    # Dynamic page routing - must be last to catch all other paths
    # Using path converter to support nested slugs like 'about/team' and 'sports/soccer'
    path('<path:slug>/', views.PageView.as_view(), name='page'),
]
