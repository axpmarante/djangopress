from django.urls import path
from news.public_views import NewsListView, NewsDetailView, NewsCategoryView

app_name = 'news'

urlpatterns = [
    path('news/', NewsListView.as_view(), name='list'),
    path('news/category/<slug:slug>/', NewsCategoryView.as_view(), name='category'),
    path('news/<slug:slug>/', NewsDetailView.as_view(), name='detail'),
]
