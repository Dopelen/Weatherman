from datetime import timedelta
from typing import Optional, Dict, Any

import openmeteo_requests
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import requests
import requests_cache
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from retry_requests import retry

from .models import CitySearch

# Настройка USER_AGENT и кэш сессии необходима для корректной работы API. Она произведена здесь.
USER_AGENT = 'MyWeatherTestApp/1.0'
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)


@csrf_exempt
def search_city(request: HttpRequest) -> HttpResponse:
    """Функция формирует представление на основе запроса пользователя выполняя для этого: get_coordinates, get_weather_forecast, graphic_designer.
    В процессе исполнения формируется график погоды, название локации на английском языке, температурные диапазоны для отрисовки графика погоды,
    текущая температура.
    Каждая из функций возвращает данные для формирования итогового представления.

    Параметры:
    request (HttpRequest): HTTP-запрос, содержащий данные от пользователя.

    Возвращает:
    HttpResponse: HTTP-ответ с HTML-страницей, содержащей данные о погоде и график.
    """

    graph_html = None
    csrf_token = get_token(request)

    if request.method == 'POST':
        city_name = request.POST.get('city_name')
        coordinates = get_coordinates(city_name)

        if coordinates:
            latitude = float(coordinates['lat'])
            longitude = float(coordinates['lon'])
            name = coordinates.get('name', city_name)

            weather_data = get_weather_forecast(latitude, longitude)

            if not weather_data.empty:
                current_time = pd.Timestamp.now(tz='UTC')
                offset = timedelta(hours=3)
                current_time_local = current_time + offset
                nearest_time = weather_data.iloc[(weather_data['date'] - current_time_local).abs().argsort()[0]]
                current_temperature = round(nearest_time['temperature_2m'], 1)
                current_city = f"Weather in {name}"
                graph_html = create_weather_plot(weather_data)
                city, created = CitySearch.objects.get_or_create(city_name=name)
                city.search_count += 1
                city.save()
            else:
                current_city = f"No weather data available for \"{city_name}\""
                current_temperature = None
        else:
            current_city = f"\"{city_name}\" not found"
            current_temperature = None

        cities = CitySearch.objects.all().order_by("-search_count")

        return render(request, 'weather/search.html', {
            'cities': cities,
            'graph': graph_html,
            'current_city': current_city,
            "csrf_token": csrf_token,
            "current_temperature": current_temperature
        })
    return render(request, 'weather/search.html', {"csrf_token": csrf_token})


def get_coordinates(city_name: str) -> Optional[Dict[str, Any]]:
    """Функция получает на вход строковое значение "название города" и отправляет его через API для получения географических данных указанного места и его названия на английском языке.
    Если данная локация не обладает описанием на английском языке, пришедшие данные будут на языке, на котором локация была внесена на сайт.
    Возвращает json или None, если данные не найдены.
    """

    url = f"https://nominatim.openstreetmap.org/search?q={city_name}&format=json&limit=1"
    headers = {
        'User-Agent': USER_AGENT,
        "Accept-Language": "en",
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data:
                return data[0]
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
    return None


def get_weather_forecast(latitude: float, longitude: float) -> pd.DataFrame:
    """Функция получает на вход пару координат в формате float, и отправляет их через API для получения данных по погоде в этой точке.
    Полученные данные преобразуются в pandas DataFrame и являются возвращаемым значением функции."""

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


def create_weather_plot(weather_data: pd.DataFrame) -> str:
    """Эта функция формирует график погоды для отображения и возвращает его в виде html строки"""
    min_temp = weather_data['temperature_2m'].min() - 2
    max_temp = weather_data['temperature_2m'].max() + 2
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=weather_data['date'],
                   y=weather_data['temperature_2m'],
                   mode='lines',
                   fill='tozeroy',
                   fillcolor='rgba(193, 227, 255, 0.6)',
                   line=dict(color='rgba(0,95,153,1)', width=3),
                   hovertemplate='<br>'.join([
                       'Day: %{x|%d}',
                       'Month: %{x|%b}',
                       'Hour: %{x|%H:%M}',
                       'Temperature: %{y:.1f}°C',
                       '<extra></extra>'
                   ])
                   )
    )
    fig.update_layout(
        dragmode=False,
        title={
            'text': 'Hourly Temperature',
            'font': {
                'family': 'BioRhyme, serif',
                'size': 36,
                'color': 'black'
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
        ),
        plot_bgcolor='rgba(240, 248, 255, 0.9)',  # Фон самого графика
        hoverlabel=dict(
            bgcolor='rgba(193, 227, 255, 1.0)',  # Фон подсказки
            font=dict(
                color='black'  # Цвет текста подсказки
            )
        )
    )
    config = {'displayModeBar': False,
              'editable': False,
              "edits": False,
              "scrollZoom": False,
              "showAxisDragHandles": False,
              }
    return pio.to_html(fig, full_html=False, config=config)

# def city_suggestions(request):
# """Эта функция отвечает за автодополнение поля ввода"""
#     query = request.GET.get('query', '')
#     if query:
#         cities = CitySearch.objects.filter(city_name__icontains(query)).order_by('-search_count')[:5]
#         suggestions = [city.city_name for city in cities]
#     else:
#         suggestions = []
#     return JsonResponse(suggestions, safe=False)
