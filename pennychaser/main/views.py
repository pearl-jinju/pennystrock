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
        data = StockPriceData.objects.filter(ticker__iexact=ticker).order_by('-date')[:30]
        if not data.exists():
            return Response({
                'ticker': ticker,
                'name': name,
                'data': []
            }, status=200)

        # 결과 구성
        result = [
            {
                'date': stock.date.strftime('%Y-%m-%d'),
                'open': round(stock.open, 4),
                'high': round(stock.high, 4),
                'low': round(stock.low, 4),
                'close': round(stock.close, 4),
                'volume': stock.volume,
                'ema_112': round(stock.ema_112, 4) if stock.ema_112 else None,
                'ema_224': round(stock.ema_224, 4) if stock.ema_224 else None,
                'macd': round(stock.macd, 4) if stock.macd else None,
                'macd_signal': round(stock.macd_signal, 4) if stock.macd_signal else None,
                'rsi_14': round(stock.rsi_14, 4) if stock.rsi_14 else None,
                'bollinger_high': round(stock.bollinger_high, 4) if stock.bollinger_high else None,
                'bollinger_low': round(stock.bollinger_low, 4) if stock.bollinger_low else None,
                'stochastic_k': round(stock.stochastic_k, 4) if stock.stochastic_k else None,
                'stochastic_d': round(stock.stochastic_d, 4) if stock.stochastic_d else None,
            }
            for stock in data
        ]

        return Response({'ticker': ticker, 'name': name, 'data': result})


class TechData(APIView):
    """
    종목별 가격정보를 가져옴
    """
    def get(self, request): 
        db_list = StockData.objects.filter(last_price__gt=1.0, last_price__lte=5.0).only('ticker')
        
        ticker_list = []
        name_list = []
        for db in db_list:
            ticker_list.append(db.ticker)
            name_list.append(db.name)

        # print(len(ticker_list))
        
        for stock_ticker, stock_name in tqdm(zip(ticker_list,name_list)):
                
            stock_df = yf.download(stock_ticker, period='max',progress=False).reset_index()

            # StockPriceData.objects.all().delete()
            # 조기 종료1. 데이터의 무존재
            if len(stock_df)==0:
                continue
            
            
            # 조기 종료2. 기존의 DB에 있는경우
            if StockPriceData.objects.filter(name= stock_name,date=stock_df['Date'].iloc[-1]).count() >= 1:
                print("이미 최신 정보입니다.")
                continue

            # 조기종료3. 최소 3년 이상의 데이터 검증 필요
            if len(stock_df) < 224*3:
                print("주가 정보가 너무 적음, 최소 3년이상의 데이터 필요")
                continue

            # 이중인덱스 제거
            stock_df.columns = stock_df.columns.droplevel(1)
            # 주가 분석 지표 생성
            # --지수이동평균선 (최대 3년까지 )
            stock_df['EMA_112'] = ta.trend.ema_indicator(close=stock_df['Close'], window=112)
            stock_df['EMA_224'] = ta.trend.ema_indicator(close=stock_df['Close'], window=224)
            stock_df['EMA_448'] = ta.trend.ema_indicator(close=stock_df['Close'], window=448)
            stock_df['EMA_672'] = ta.trend.ema_indicator(close=stock_df['Close'], window=672)

            # --MACD OSC
            macd = ta.trend.MACD(close=stock_df['Close'])
            stock_df['MACD'] = macd.macd()
            stock_df['MACD_signal'] = macd.macd_signal()
            stock_df['MACD_diff'] = macd.macd_diff()

            # --RSI
            rsi_indicator = ta.momentum.RSIIndicator(close=stock_df['Close'], window=14)
            stock_df['RSI_14'] = rsi_indicator.rsi()


            # --Bolinger Band
            bollinger = ta.volatility.BollingerBands(close=stock_df['Close'], window=20, window_dev=2)
            stock_df['Bollinger_High'] = bollinger.bollinger_hband()
            stock_df['Bollinger_Low'] = bollinger.bollinger_lband()

            # --Stochastic
            stochastic = ta.momentum.StochasticOscillator(
                high=stock_df['High'],
                low=stock_df['Low'],
                close=stock_df['Close'],
                window=14,
                smooth_window=3
                )
            stock_df['Stochastic_K'] = stochastic.stoch()
            stock_df['Stochastic_D'] = stochastic.stoch_signal()

            # --Parabolic SAR
            psar = ta.trend.PSARIndicator(
                high=stock_df['High'],
                low=stock_df['Low'],
                close=stock_df['Close'],
                step=0.02,
                max_step=0.18
            )
            stock_df['PSAR'] = psar.psar()

            # --OBV
            obv = ta.volume.OnBalanceVolumeIndicator(close=stock_df['Close'], volume=stock_df['Volume'])
            stock_df['OBV'] = obv.on_balance_volume()
            
            # 결측치 모두 제거
            stock_df.dropna(inplace=True)
            # 이름과 티커 넣기
            stock_df.insert(0, 'ticker', stock_ticker)
            stock_df.insert(0, 'name', stock_name)


            stock_objects = [
            StockPriceData(
                name=row['name'],
                ticker=row['ticker'],
                date=row['Date'],
                close=row['Close'],
                high=row['High'],
                low=row['Low'],
                open=row['Open'],
                volume=row['Volume'],
                ema_112=row['EMA_112'],
                ema_224=row['EMA_224'],
                ema_448=row['EMA_448'],
                ema_672=row['EMA_672'],
                macd=row['MACD'],
                macd_signal=row['MACD_signal'],
                macd_diff=row['MACD_diff'],
                rsi_14=row['RSI_14'],
                bollinger_high=row['Bollinger_High'],
                bollinger_low=row['Bollinger_Low'],
                stochastic_k=row['Stochastic_K'],
                stochastic_d=row['Stochastic_D'],
                psar=row['PSAR'],
                obv=row['OBV'],
            )
            for index, row in stock_df.iterrows()
        ]

            # bulk_create를 사용하여 데이터 삽입 (중복은 무시)
            StockPriceData.objects.bulk_create(stock_objects, ignore_conflicts=True)

        return JsonResponse({}, status=200)


class TickerNameLoad(APIView):
    """
    현재 확보한 데이터의 이름과 티커를 가져옴
    """
    def get(self, request): 
        TickerName.objects.all().delete()
        ticker_data = list(StockPriceData.objects.values_list('ticker', flat=True).distinct())
        ticker_data = list(dict.fromkeys(ticker_data))

        name_data = list(StockPriceData.objects.values_list('name', flat=True).distinct())
        name_data = list(dict.fromkeys(name_data))


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