from django.urls import path

from .views import SaveData, GetData, TechData, TickerNameLoad, AutocompleteView, Main


urlpatterns = [
    path('', Main.index, name='index'),
    path('save-data/', SaveData.as_view()),
    path('tech-data/', TechData.as_view()),
    path('ticker-name-data/', TickerNameLoad.as_view()),
    path('get-data/', GetData.as_view(), name='get_data'),

    # 자동완성기능
    path('autocomplete/', AutocompleteView.as_view(), name='autocomplete'),

]