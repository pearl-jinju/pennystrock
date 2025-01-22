from django.db import models

class StockData(models.Model):
    ticker           = models.TextField()   # Symbol(티커)
    name             = models.TextField()   # Name(종목명)
    last_price       = models.FloatField()   # Last Sale(최근 종가)
    market_cap       = models.IntegerField()   # Market Cap(시가총액)
    country          = models.TextField()   # Country(국가)
    sector           = models.TextField()   # Sector(섹터)
    industry         = models.TextField()   # Industry(업종)
    
# 주가 가격 관련 기술적 분석 지표 데이터터
class StockPriceData(models.Model):
    name = models.CharField(max_length=100)  # 주식 이름
    ticker = models.CharField(max_length=10)  # 주식 티커 심볼
    date = models.DateField()  # 날짜
    close = models.FloatField()  # 종가
    high = models.FloatField()  # 고가
    low = models.FloatField()  # 저가
    open = models.FloatField()  # 시가
    volume = models.BigIntegerField()  # 거래량
    # 기술 지표들
    ema_112 = models.FloatField(null=True, blank=True)
    ema_224 = models.FloatField(null=True, blank=True)
    ema_448 = models.FloatField(null=True, blank=True)
    ema_672 = models.FloatField(null=True, blank=True)
    macd = models.FloatField(null=True, blank=True)
    macd_signal = models.FloatField(null=True, blank=True)
    macd_diff = models.FloatField(null=True, blank=True)
    rsi_14 = models.FloatField(null=True, blank=True)
    bollinger_high = models.FloatField(null=True, blank=True)
    bollinger_low = models.FloatField(null=True, blank=True)
    stochastic_k = models.FloatField(null=True, blank=True)
    stochastic_d = models.FloatField(null=True, blank=True)
    psar = models.FloatField(null=True, blank=True)
    obv = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.ticker}) on {self.date}"

    class Meta:
        unique_together = ('ticker', 'date')  # 중복 방지를 위한 고유 제약 조건
        # 또는 Django 3.2 이상에서는 다음과 같이 UniqueConstraint를 사용할 수 있습니다.
        # constraints = [
        #     models.UniqueConstraint(fields=['ticker', 'date'], name='unique_ticker_date')
        # ]
        ordering = ['ticker', 'date']  # 정렬 기준 설정 (선택 사항)


class TickerName(models.Model):
    ticker = models.CharField(max_length=10)  # 예: AAPL
    name = models.CharField(max_length=100)  # 예: Apple Inc.

    def __str__(self):
        return f"{self.name} ({self.ticker})"
    