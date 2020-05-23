import time
from urllib.request import urlopen

from apscheduler.schedulers.background import BackgroundScheduler

# 달러/원 환율 크롤러
from bs4 import BeautifulSoup


def cur_rate():
    html = urlopen("https://finance.yahoo.com/quote/KRW=X?p=KRW=X")

    bsObject = BeautifulSoup(html, "html.parser")
    bsObject = bsObject.find('div', {'id': "quote-header-info"}).find('span', {'data-reactid': '14'}).text
    bsObject = bsObject.replace(",", "")

    return float(bsObject)


class Manager():
    # [ub_client, bn_client]
    CLIENT = []

    # [ub_manager, bn_manager]
    MANAGER = []
    # {"UB":{"BTC":0.00021, "ETH":0.033}, "BN":{"BTC":0.00011, "ETH":0.0011}}
    MANAGER_ACCOUNT = {}

    # {"UB":212121, "BN":111113}
    MANAGER_TOTAL_MONEY = {}

    # 현재 돌아가는 알고리즘
    # {"UB":["will","mmm"]}
    MANAGER_ALGOSET = {}
    MANAGER_PROFIT = {}

    def __init__(self, client):
        # 혹여나 거래소 구분이 필요할까 하여 (UPBIT, BINANCE 두가지 존재)
        '''
        exchanges
        1. UB
        2. BN
        '''
        self.exchange = client.EXCHANGE
        self.client = client

        # 등록
        # 클라이언트 관리자
        Manager.CLIENT.append(self.client)

        # 매니저 관리자
        Manager.MANAGER.append(self)
        Manager.MANAGER_ALGOSET[self.exchange] = []

        # 잔액관리
        self.having_asset = self.m_account_bal()
        Manager.MANAGER_ACCOUNT[self.exchange] = self.having_asset

        # 잔고 카운팅 기본단위
        self.total_asset = self.m_cal_balance()
        Manager.MANAGER_TOTAL_MONEY[self.exchange] = self.total_asset

        # 현재 적용된 알고리즘
        self.running_algo = []

    @classmethod
    def monitor(cls):
        target = Manager.MANAGER

        for i in range(len(target)):
            mn = target[i]
            # account 모니터
            having_asset = mn.m_account_bal()
            Manager.MANAGER_ACCOUNT[mn.exchange] = having_asset

            # 잔액 모니터
            total_asset = mn.m_cal_balance()
            Manager.MANAGER_TOTAL_MONEY[mn.exchange] = total_asset

        # 매 정시 알고리즘별 금액 세팅
        sched = BackgroundScheduler()
        sched.start()
        sched.add_job(Manager.m_set_money, 'cron', hour=0, minute=0, second=0, id="m_set_money")

        while True:
            time.sleep(1)

    # 매 정시마다 각 알고리즘별 금액세팅 (수익과 위험을 기준으로)
    @classmethod
    def m_set_money(cls):
        # 우선은 잔고대비 99%
        rebalancing = {}

        ex_list = list(dict.keys(Manager.MANAGER_TOTAL_MONEY))
        for i in range(len(ex_list)):
            ex = ex_list[i]
            rebalancing[ex] = int(Manager.MANAGER_TOTAL_MONEY[ex] * 0.99)
        return rebalancing

    # 정시 초기화
    def initializer(self):
        # 연결된 알고리즘 평가

        # 리벨런싱
        pass

    # 잔고관리
    def m_account_bal(self):
        account = self.client.account_info()
        account_data = {}
        for i in range(len(account)):
            account_data[account[i]['currency']] = float(account[i]['balance']) + float(account[i]['locked'])

        return account_data

    # 잔고 원화 추정치
    # 수수료 명목으로 bnb 코인 일부분 잔고에서 제외
    def m_cal_balance(self):
        default_unit = self.client.DEFAULT_UNIT
        if default_unit == "KRW":
            currency_rate = 1
            for_fee = 0
        elif default_unit == "USDT":
            currency_rate = cur_rate()
            for_fee = 4

        balance = 0
        asset_list = self.having_asset
        key_list = list(asset_list.keys())

        for i in range(len(key_list)):
            ticker = key_list[i]
            if ticker == default_unit:
                balance += float(asset_list[ticker])
            else:
                market = self.m_market(ticker)
                price = float(self.client.get_current_price(market)[0]['price']) * float(asset_list[ticker])

                balance += price
        balance = balance - for_fee
        return balance

    def m_market(self, market):
        if self.exchange == "UB":
            return "KRW-" + market
        elif self.exchange == "BN":
            return market + "USDT"

    def m_apply_algo(self, algo_name):
        self.running_algo.append(algo_name)

    def m_delete_algo(self, algo_name):
        # self.running_algo.remove(algo_name)
        pass