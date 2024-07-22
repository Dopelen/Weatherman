from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import openmeteo_requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import requests
import requests_cache
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from retry_requests import retry

from .forms import CityForm
from .models import CitySearch

USER_AGENT = 'MyWeatherTestApp/1.0'
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)


def get_weather_forecast(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": {latitude},
        "longitude": {longitude},
        "hourly": "temperature_2m",
        "forecast_days": 2,
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]
    hourly = response.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()

    hourly_data = {"date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left"), "temperature_2m": hourly_temperature_2m}
    hourly_dataframe = pd.DataFrame(data=hourly_data)
    return hourly_dataframe


def get_coordinates(city_name):
    url = f"https://nominatim.openstreetmap.org/search?q={city_name}&format=json&limit=1"
    headers = {
        'User-Agent': USER_AGENT,
        "Accept-Language": "en",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data:
            return data[0]
    return None


def search_city(request):
    graph_html = None
    print(f"Request method: {request.method}")
    csrf_token = get_token(request)

    if request.method == 'POST':
        city_name = request.POST.get('city_name')
        print(f"Имя города: {city_name}")
        coordinates = get_coordinates(city_name)

        if coordinates:
            print(coordinates)
            latitude = coordinates['lat']
            longitude = coordinates['lon']
            name = coordinates['name']

            weather_data = get_weather_forecast(latitude, longitude)
            current_time = pd.Timestamp.now(tz='UTC')
            offset = timedelta(hours=3)
            current_time_local = current_time + offset
            nearest_time = weather_data.iloc[(weather_data['date'] - current_time_local).abs().argsort()[0]]

            current_temperature = round(nearest_time['temperature_2m'], 1)
            current_city = f"Weather in {name}"

            min_temp = weather_data['temperature_2m'].min() - 2
            max_temp = weather_data['temperature_2m'].max() + 2

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(x=weather_data['date'],
                           y=weather_data['temperature_2m'],
                           mode='lines',
                           fill='tozeroy',
                           fillcolor='rgba(255, 255, 0, 0.4)',
                           line=dict(color='#FFD700', width=2),
                           hovertemplate='<br>'.join([
                               'Day: %{x|%d}',
                               'Month: %{x|%b}',
                               'Hour: %{x|%H:%M}',
                               'Temperature: %{y:.1f}°C',
                               '<extra></extra>'  # Убирает дополнительный текст, например, название серии
                           ])
                           )
            )
            fig.update_layout(
                dragmode=False,
                title={
                    'text': 'Hourly Temperature',
                    'font': {
                        'family': 'BioRhyme, serif',  # Шрифт заголовка
                        'size': 36,  # Размер шрифта
                        'color': 'black'  # Цвет шрифта
                    },
                    'x': 0.5,
                    'xanchor': 'center',
                    'yanchor': 'top'
                },
                xaxis_title={
                    'text': 'Time and date',
                    'font': {
                        'family': 'BioRhyme, serif',
                        'size': 24,
                        'color': 'black'
                    }
                },
                yaxis_title={
                    'text': 'Temperature°C',
                    'font': {
                        'family': 'BioRhyme, serif',
                        'size': 20,
                        'color': 'black'
                    }
                },
                xaxis=dict(
                    dtick=7200000,
                    tickformat="%H\n%d%b",
                    ticklabelmode="period",
                    tickangle=45
                ),
                yaxis=dict(
                    dtick=1,
                    range=[min_temp, max_temp]
                )
            )

            config = {'displayModeBar': False,
                      'editable': False,
                      "edits": False,
                      "scrollZoom": False,
                      "showAxisDragHandles": False,
                      }
            graph_html = pio.to_html(fig, full_html=False, config=config)

            city, created = CitySearch.objects.get_or_create(city_name=name)
            city.search_count += 1
            city.save()
        else:
            current_city = "City not found"
            current_temperature = None

        cities = CitySearch.objects.all()
        # if cities.exists():
        #     last_city = cities.first().city_name
        #     message = last_city
        # else:
        #     message = "You haven't searched our weather yet"

        return render(request, 'weather/search.html',
                      {'cities': cities, 'graph': graph_html,
                       'current_city': current_city, "csrf_token": csrf_token,
                       "current_temperature": current_temperature})

    return render(request, 'weather/search.html', {"csrf_token": csrf_token}, )

# def get_translated_city_name(city_name):
#     endpoint = "https://nominatim.openstreetmap.org/search"
#     headers = {
#         'User-Agent': USER_AGENT,
#     }
#     params = {
#         'q': city_name,
#         'format': 'json',
#         'addressdetails': 1,
#         'accept-language': 'en'
#     }
#     response = requests.get(endpoint, params=params, headers=headers)
#     result = response.json()
#     if result:
#         return result[0]['display_name']
#     return None


# def city_suggestions(request):
#     query = request.GET.get('query', '')
#     if query:
#         cities = CitySearch.objects.filter(city_name__icontains(query)).order_by('-search_count')[:5]
#         suggestions = [city.city_name for city in cities]
#     else:
#         suggestions = []
#     return JsonResponse(suggestions, safe=False)
