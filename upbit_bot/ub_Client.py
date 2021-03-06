import asyncio
import datetime
import hashlib
import json
import threading
import time
import uuid
from urllib.parse import urlencode

import jwt
import numpy
import requests
import websockets
from pytz import timezone

from upbit_bot.config.realtype import RealType


class Ub_Client():
    EXCHANGE = "UB"
    HOST = 'https://api.upbit.com'
    DEFAULT_UNIT = "KRW"

    TR_FEE = 0.002

    # 최종거래가격
    CUR_PRICE = {}

    # 최우선매도호가
    PRIOR_SELL_PRICE = {}
    # 최우선매수호가
    PRIOR_BUY_PRICE = {}

    def __init__(self, api_key, sec_key):
        self.A_key = api_key
        self.S_key = sec_key

        self.realtype = RealType()

        # william 알고리즘 위한 데이터 세팅
        self.W1_data_amount_for_param = 200  # max limit 이 200개

    # 코드리스트 요청
    @classmethod
    def get_code_list(cls, base_market):
        url = "https://api.upbit.com/v1/market/all"
        querystring = {"isDetails": "false"}
        markets = requests.request("GET", url, params=querystring).json()

        tickers = []

        for market in markets:
            if base_market in market['market']:
                tickers.append(market['market'])

        return tickers

    # 현재가 웹소켓
    @classmethod
    async def w_current_price(cls, volume=0):
        uri = "wss://api.upbit.com/websocket/v1"
        code_list = cls.get_code_list("KRW")
        async with websockets.connect(uri) as websocket:
            send_data = json.dumps([{"ticket": "UNIQUE_TICKET"}, {"type": "orderbook",
                                                                  "codes": code_list
                                                                  }])
            # 데이터 요청
            await websocket.send(send_data)

            while True:
                # time.sleep(0.01)
                time.sleep(1)
                rec_data = json.loads(await websocket.recv())
                Ub_Client.CUR_PRICE[rec_data['code']] = rec_data['orderbook_units'][0]['ask_price']
                Ub_Client.PRIOR_SELL_PRICE[rec_data['code']] = rec_data['orderbook_units'][0]['bid_price']
                Ub_Client.PRIOR_BUY_PRICE[rec_data['code']] = rec_data['orderbook_units'][0]['ask_price']
                print(rec_data)

    # 현재 계정 데이터 요청
    def account_info(self):
        endpoint = "/v1/accounts"

        payload = {
            'access_key': self.A_key,
            'nonce': str(uuid.uuid4()),
        }

        jwt_token = jwt.encode(payload, self.S_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        url = Ub_Client.HOST + endpoint

        res = requests.get(url, headers=headers)
        return res.json()


    # 차트봉요청
    def get_candle(market, count, interval='days', unit=None):
        '''
        :param market: 요청하는 마켓
        :param count: 요청 갯수
        :param unit: 단위 (day, minutes, months, weeks)
        :return:
        '''
        endpoint = "/v1/candles/" + interval + '/' + str(unit if unit else '')
        querystring = {"market": str(market), "count": str(count), "convertingPriceUnit": "KRW"}

        res = requests.get('https://api.upbit.com' + endpoint, params=querystring).json()
            # [
            #     {
            #         "market": "KRW-BTC",
            #         "candle_date_time_utc": "2018-04-18T00:00:00",
            #         "candle_date_time_kst": "2018-04-18T09:00:00",
            #         "opening_price": 8450000,
            #         "high_price": 8679000,
            #         "low_price": 8445000,
            #         "trade_price": 8626000,
            #         "timestamp": 1524046650532,
            #         "candle_acc_trade_price": 107184005903.68721,
            #         "candle_acc_trade_volume": 12505.93101659,
            #         "prev_closing_price": 8450000,
            #         "change_price": 176000,
            #         "change_rate": 0.0208284024
            #     }, ...
            # ]
        return res

    # 현재가 데이터를 가져오기 위한 함수 // not websocket
    def get_current_price(self, market):
        endpoint = "/v1/ticker"
        querystring = {"markets": market}

        url = Ub_Client.HOST + endpoint

        response = requests.request("GET", url, params=querystring).json()

        data = []
        data_dict = {
            'market': market,
            "price": float(response[0]['trade_price'])
        }
        data.append(data_dict)

        return data

    # 시장가/지정가 매수매도
    def new_order(self, market, side, ord_type, vol=None, money=None, target=None):

        if (target and money) is not None:
            target = self.price_cal(market, target)
            vol = round(money / target, 8)

        elif target is not None:
            target = self.price_cal(market, target)

        if ord_type == "limit":
            query = {
                'market': market,
                'side': side,
                'volume': vol,
                'price': target,
                'ord_type': "limit",
            }
        elif ord_type == "price":
            query = {
                'market': market,
                'side': side,
                'price': money,
                'ord_type': "price",
            }
        elif ord_type == "market":
            query = {
                'market': market,
                'side': side,
                'volume': vol,
                'ord_type': "market",
            }
        query_string = urlencode(query).encode()

        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()

        payload = {
            'access_key': self.A_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }

        jwt_token = jwt.encode(payload, self.S_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.post(Ub_Client.HOST + "/v1/orders", params=query, headers=headers).json()

        if res['ord_type'] == 'limit':
            ord_price = res['price']
            ord_volume = res['volume']

        else:
            ord_price = None
            ord_volume = None

        data = []
        data_dict = {
            "market": res['market'],
            "side": res['side'],
            "ord_type": res['ord_type'],
            "ord_price": ord_price,
            "ord_volume": ord_volume,
            "uuid": res['uuid'],
            'created_at': res['created_at']
        }
        data.append(data_dict)

        return data

    # 개별 주문 조회
    def query_order(self, req):
        query = {
            'uuid': req[0]['uuid'],
        }
        query_string = urlencode(query).encode()

        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()

        payload = {
            'access_key': self.A_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }

        jwt_token = jwt.encode(payload, self.S_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.get(Ub_Client.HOST + "/v1/order", params=query, headers=headers).json()

        if len(res['trades']) > 0:
            ord_price = res['trades'][0]['price']
            ord_volume = res['trades'][0]['volume']

        else:
            ord_price = res['price']
            ord_volume = res['volume']

        data = []
        data_dict = {
            "market": res['market'],
            "created_at": res['created_at'],
            "side": res['side'],
            "ord_type": res['ord_type'],
            "status": res["state"],
            "uuid": res['uuid'],
            "ord_price": ord_price,
            "ord_volume": ord_volume,
            "executed_volume": res["executed_volume"]
        }
        data.append(data_dict)

        return data

    ## uuid 기반 기주문 취소 요청
    def cancel_order(self, req):
        query = {
            'uuid': req["uuid"],
        }
        query_string = urlencode(query).encode()

        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()

        payload = {
            'access_key': self.A_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }

        jwt_token = jwt.encode(payload, self.S_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.delete(Ub_Client.HOST + "/v1/order", params=query, headers=headers).json()

        return res

    # 현재 대기열에 있는 주문 uuid 들의 값들을 가져옴
    def uuids_by_state(self, situation, ordered_uuids):
        query = {
            'state': situation,
        }
        query_string = urlencode(query)

        uuids = ordered_uuids
        uuids_query_string = '&'.join(["uuids[]={}".format(_uuid) for _uuid in uuids])

        query['uuids[]'] = uuids
        if len(query['uuids[]']) == 0:
            return []

        query_string = "{0}&{1}".format(query_string, uuids_query_string).encode()

        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()

        payload = {
            'access_key': self.A_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }

        jwt_token = jwt.encode(payload, self.S_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.get(Ub_Client.HOST + "/v1/orders", params=query, headers=headers)

        return res.json()

    def price_cal(self, market, ord_price):
        if ord_price < 10:
            min_unit = 0.01
        elif ord_price < 100:
            min_unit = 0.1
        elif ord_price < 1000:
            min_unit = 1
        elif ord_price < 10000:
            min_unit = 5
        elif ord_price < 100000:
            min_unit = 10
        elif ord_price < 500000:
            min_unit = 50
        elif ord_price < 1000000:
            min_unit = 100
        elif ord_price < 2000000:
            min_unit = 500
        else:
            min_unit = 1000

        # 타겟 가격 보다 내림가격(살땐 천천히 팔땐 빨리)
        poss_price = numpy.floor(ord_price / min_unit) * min_unit
        return round(poss_price, 2)
