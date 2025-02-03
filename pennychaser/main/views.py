from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse


# views 관련 import
import ta.momentum
import ta.volatility
from yahoo_fin import stock_info as si
import yfinance as yf
import pandas as pd
import numpy as np
from tqdm import tqdm
import datetime
import re

# DB관련 import 
from django.db import transaction
from .models import StockData, StockPriceData, TickerName
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status


# ta 관련 import
import pandas as pd
import ta


# pickle
import pickle


def stock_basic_data(stock_ticker, stock_name,array=False):
    stock_df = yf.download(stock_ticker, period='max',progress=False).reset_index()

    # StockPriceData.objects.all().delete()
    # 조기 종료1. 데이터의 무존재
    if len(stock_df)==0:
        stock_df = None
        return stock_df
    

    
    # 1. 기본 주가데이터==============================
    
    # 이중인덱스 제거
    stock_df.columns = stock_df.columns.droplevel(1)
    # 이름과 티커 넣기
    stock_df.insert(0, 'ticker', stock_ticker)
    stock_df.insert(0, 'name', stock_name)

    # 시고저종,거래량 % 
    stock_df['Close_rate'] = round((stock_df['Close']/stock_df['Close'].shift(1)-1)*100,2)
    stock_df['High_rate'] =  round((stock_df['High']/stock_df['High'].shift(1)-1)*100,2)
    stock_df['Low_rate'] =  round((stock_df['Low']/stock_df['Low'].shift(1)-1)*100,2)
    stock_df['Open_rate'] =  round((stock_df['Open']/stock_df['Open'].shift(1)-1)*100,2)
    stock_df['Volume_rate'] =  round((stock_df['Volume']/stock_df['Volume'].shift(1)-1)*100,2)


    # 2. 기술적분석 주가데이터(당일 기술적 분석 데이터가 아니라 전일 데이터를 사용)==============================
    # 이동평균선은 주가에 반영되어있으므로 제외한다.
    # --MACD OSC
    macd = ta.trend.MACD(close=stock_df['Close'])
    for i in range(1,6):
        stock_df[f'MACD_signal_{i}'] = macd.macd_signal().shift(i)
    for i in range(1,6):
        stock_df[f'MACD_diff{i}'] = macd.macd_diff().shift(i)

    # --RSI
    rsi_indicator = ta.momentum.RSIIndicator(close=stock_df['Close'], window=14)
    for i in range(1,6):
        stock_df[f'RSI_{i}'] = rsi_indicator.rsi().shift(i)

    # # --Bolinger Band
    bollinger = ta.volatility.BollingerBands(close=stock_df['Close'], window=20, window_dev=2)
    for i in range(1,6):
        stock_df[f'Bollinger_High_{i}'] = bollinger.bollinger_hband().shift(i)/stock_df['Close'].shift(i)
    for i in range(1,6):
        stock_df[f'Bollinger_Low_{i}'] = bollinger.bollinger_lband().shift(i)/stock_df['Close'].shift(i)


    # --Stochastic
    stochastic = ta.momentum.StochasticOscillator(
        high=stock_df['High'],
        low=stock_df['Low'],
        close=stock_df['Close'],
        window=14,
        smooth_window=3
        )
    for i in range(1,6):
        stock_df[f'Stochastic_K_{i}'] = stochastic.stoch().shift(i)
    for i in range(1,6):
        stock_df[f'Stochastic_D_{i}'] = stochastic.stoch_signal().shift(i)

    # --Parabolic SAR
    psar = ta.trend.PSARIndicator(
        high=stock_df['High'],
        low=stock_df['Low'],
        close=stock_df['Close'],
        step=0.02,
        max_step=0.18
    )
    for i in range(1,6):
        stock_df[f'PSAR_{i}'] = psar.psar().shift(i)/stock_df['Close'].shift(i)

    # market Data 추가
    # 시작데이터 가져오기
    loaded_df = pd.read_pickle("market_data.pkl")
    loaded_df = loaded_df.reset_index()
    loaded_df['Date']=loaded_df['Date'].apply(lambda x : str(x)[:10])

    stock_df['Date']=stock_df['Date'].apply(lambda x : str(x)[:10])

    stock_df = pd.concat([stock_df.set_index('Date'), loaded_df.set_index('Date')], axis=1, join='inner').dropna()

    stock_df = stock_df.reset_index()

    stock_df = stock_df.dropna()

    if array == True:
        return stock_df.iloc[-1:,:]
    else:
        return stock_df

class SaveData(APIView):
    """
    티커 정보 최신화 기능
    https://www.nasdaq.com/market-activity/stocks/screener?page=1&rows_per_page=25
    에서 다운받아 폴더에 넣을것
    """
    def get(self, request): 
        # # session 사용 예시 (값 가져오기, 없다면 저장)
        # quiz_count = int(request.session.get('quiz_count',1))
        # # session 사용 예시 (값 가져오기)
        # quiz_id = int(request.session.get('quiz_id'))
        # session 저장 예시 
        # request.session['quiz_count'] = int(quiz_count)+1
        
        # 데이터 저장 시작('티커 데이터 경로 : https://www.nasdaq.com/market-activity/stocks/screener?page=1&rows_per_page=25')
        # 2. 기존데이터 모두 제거
        StockData.objects.all().delete()
        link_list = [
            'nasdaq_screener.csv',
            'nasdaq_screener2.csv',
            'nasdaq_screener3.csv',
            ]

        for link in link_list:
            df = pd.read_csv( link, encoding='cp949')
            # 1. Ticker 불러오기
            # 1-1. 데이터 무결성을 위한 결측치 처리 시가총액 결측치 0 변경
            df['Market Cap'] = df['Market Cap'].fillna(0)
            # 1-2. 결측치 제거 섹터 및 업종 결측치 "-" 변경 
            df = df[['Symbol', 'Name', 'Last Sale','Market Cap','Country',  'Sector', 'Industry']].fillna('-')
            # 1-3. $표시 제거 
            df['Last Sale'] = df['Last Sale'].apply(lambda x :float(x[1:]))
            # 1-4. ticker 소문자 변형
            # 정규표현식 패턴: '/' 뒤에 오는 한 대문자
            pattern = r'/([A-Z])'
            # 치환 함수: 그룹 1의 문자를 소문자로 변환
            replacement = lambda m: m.group(1).lower()
            df['Symbol'] =  df['Symbol'].apply(lambda x : re.sub(pattern, replacement, x))
            # 정규표현식 패턴: '/' 뒤에 오는 한 대문자
            pattern = r'\^([A-Z])'
            # 치환 함수: 그룹 1의 문자를 소문자로 변환
            replacement = lambda m: f'_p{m.group(1).lower()}'
            df['Symbol'] =  df['Symbol'].apply(lambda x : re.sub(pattern, replacement, x)
)
            # 1-5. 새로운 데이터 저장
            data_list = []
            for idx, data in tqdm(df.iterrows()):
                data_list.append(
                    StockData(
                        ticker     = data['Symbol'], 
                        name       = data['Name'],
                        last_price = data['Last Sale'], 
                        market_cap = data['Market Cap'], 
                        country    = data['Country'], 
                        sector     = data['Sector'],
                        industry   = data['Industry'],
                    )
                )
                
            StockData.objects.bulk_create(data_list)
        # 시간 가져오기
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")   


        # stock_df = yf.download(ticker_list, period='1y').reset_index()
        # #TODO 데이터 불러오기 오류
        # print(stock_df)
        # reset_index
        # hist_data = stock.history(period="10y").reset_index()
        # hist_data['Date'] = hist_data['Date'].apply(lambda x : str(x)[:10])

        # print(hist_data)

        # 티커 리스트
        

        # 여러 티커의 데이터 다운로드
        

        # print(data)


        return JsonResponse({'message': f'저장 성공!  {now}'}, status=200)

class GetData(APIView):
    def get(self, request):
        ticker = request.GET.get('ticker', None)
        if not ticker:
            return Response({'error': 'Ticker is required.'}, status=400)
        
        # Ticker Name 가져오기
        name = TickerName.objects.filter(ticker=ticker).first()
        if name:
            name = name.name
        else:
            name = "Unknown Ticker"

        # 주가 데이터 가져오기
        loaded_df = pd.read_pickle("stock_data.pkl")
        
        print(loaded_df)
        
        # 결과 구성
 
        return Response({}, status=200)

class MarketData(APIView):
    def get(self, request): 
        """
        시장지표 데이터 저장
        """
        #  시장지표
        market_index = [
            'VIXM', 'VIXY', 'BND', 'BLV', 'BIV', 'BSV',
            'VTIP', 'GLD', 'USDU', 'VNQ', 'KBWY'
        ]

        result_df = None  # 처음에는 None으로 설정

        for market in market_index:
            df = yf.download(market, period='max', progress=False).reset_index()

            # 다중 인덱스 컬럼 확인 후 처리
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)

            # 과거 5일간 수익률 계산
            for i in range(1, 6):
                df[f'{market}_{i}'] = (((df['Close'] / df['Close'].shift(1)) - 1) * 100).shift(i)

            # 필요한 컬럼만 선택
            temp_ls = [f'{market}_{i}' for i in range(1, 6)]
            temp_ls.insert(0, "Date")
            df = df[temp_ls].set_index('Date')

            # 첫 번째 루프에서는 바로 할당, 이후에는 concat
            if result_df is None:
                result_df = df
            else:
                result_df = pd.concat([result_df, df], axis=1)

        # 최종적으로 reset_index() 한 번만 실행
        # result_df = result_df.reset_index().dropna()
        # pickle로 저장
        result_df.to_pickle("market_data.pkl")

        return JsonResponse({}, status=200)

class TechData(APIView):
    """
    종목별 가격정보를 가져옴
    """
    def get(self, request): 

        
        # db_list = StockData.objects.filter(last_price__gt=1.0, last_price__lte=5.0).only('ticker')
        
        # ticker_list = []
        # name_list = []
        # for db in db_list:
        #     ticker_list.append(db.ticker)
        #     name_list.append(db.name)

        ticker_list = ["BB"]
        name_list = ["Black_berry"]
        result_df = None  # 처음에는 None으로 설정

        for stock_ticker, stock_name in tqdm(zip(ticker_list,name_list)):
                
            stock_df = stock_basic_data(stock_ticker, stock_name,array=False)

# 예측데이터 생성
            for i in range(1,6):
                stock_df[f'period_yield_{i}'] = ((stock_df['Close'].shift(-i)/stock_df['Close'])-1)*100

            if result_df is None:
                result_df = stock_df
            else:
                result_df = pd.concat([result_df, stock_df], axis=0)

            result_df = result_df.dropna()

            

        result_df.to_pickle("stock_data.pkl")


        return JsonResponse({}, status=200)


class TickerNameLoad(APIView):
    """
    현재 확보한 데이터의 이름과 티커를 가져옴
    """
    def get(self, request): 
        
        TickerName.objects.all().delete()
        loaded_df = pd.read_pickle("stock_data.pkl")
        loaded_df = loaded_df[['name','ticker']]
        name_data = loaded_df['name'].unique().tolist()
        ticker_data = loaded_df['ticker'].unique().tolist()



        if len(ticker_data) != len(name_data):
         raise ValueError("tickers와 names의 길이가 같아야 합니다!")

        bulk_data = [
            TickerName(ticker=ticker_data[i], name=name_data[i]) 
            for i in range(len(ticker_data))
        ]

        # bulk_create로 삽입
        TickerName.objects.bulk_create(bulk_data)
        print("데이터 삽입 완료!")

        return JsonResponse({}, status=200)

class AutocompleteView(APIView):
    """
    자동완성 기능
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('query', '')  # 사용자 입력값
        if query:
            # 티커나 이름에 입력값이 포함된 데이터 검색
            results = TickerName.objects.filter(
                Q(ticker__icontains=query) | Q(name__icontains=query)
            ).values('ticker', 'name')[:10]  # 최대 10개 반환
            return JsonResponse(list(results), safe=False)
        return JsonResponse([], safe=False)


class Main(APIView):
    def index(request):
        

        # 티커 가져오기
        # sp500_tickers = si.tickers_nasdaq()
        # print(sp500_tickers)

        # # 특정 주식 데이터 다운로드 (예: Apple)
        # ticker = "BB"  # 주식 심볼울 리스트로 넣으면 됨
        # data = yf.download(ticker, start="2023-01-01", end="2023-12-31")

        # 데이터 출력
        # print(data.columns[0][0])

        return render(request,'main/index.html')