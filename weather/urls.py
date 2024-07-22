from django.urls import path
from . import views

urlpatterns = [
    path('', views.search_city, name='search_city'),
#    path('suggestions', views.city_suggestions, name='city_suggestions'),
]