#-*- coding:gbk -*-

'''
    ctp marketdata ����
    ��ctp_api�򽻵��ĵײ�ģ��
    �뱣֤��ctp_api������ز��־���װ�ڱ�ģ��

    TODO:
        ���ǵ��������, �뽫ÿ��15:20-17:00��Ϊ���ɽ���ʱ��,�Ա����ݴ���. ������Ҫ���ؿ����Ƿ���Ҫ. 
        Ŀǰ�۲�
        

'''

import time
import threading
import logging

from ..common import base
from ..common import utils
from ..common.utils import tob, tos
from ctp.futures import ApiStruct as ustruct
from ctp.futures import ApiStruct as utype
from ctp.futures import MdApi

class MdSpiDelegate(MdApi):
    '''
        ��������Ϣת����Controller
        ������Ҫ�������еĺ�Լ���滻Ϊ��׼��
        ĿǰCTP���ṩ�ļ�Ϊ��׼��,�ʲ���Ҫ�滻
    '''
    logger = logging.getLogger('ctp.MdSpiDelegate')
    
    def __init__(self,
            name,
            broker_id,   #�ڻ���˾ID
            investor_id, #Ͷ����ID
            passwd, #����
            controller,  #ʵ�ʲ�����
        ):       
        self._name = name
        self._instruments = set()
        self._broker_id =broker_id
        self._investor_id = investor_id
        self._passwd = passwd
        self._cur_day = 0    #int(time.strftime('%Y%m%d'))   #�����ܲ������ڵ�ǰϵͳ������! #��ǰ��ʵ�ʽ�����. ҹ�̹��뵱��,���Ǵ���!!
        self._controller = controller
        self._request_id = 0

    def inc_request_id(self):
        self._request_id += 1
        return self._request_id

    def checkErrorRspInfo(self, info):
        logging.debug(info)
        if info.ErrorID !=0:
            self.logger.error("MD:ErrorID:%s,ErrorMsg:%s" %(info.ErrorID,tos(info.ErrorMsg)))
        return info.ErrorID !=0

    def OnRspError(self, info, RequestId, IsLast):
        self.logger.error('MD:requestID:%s,IsLast:%s,info:%s' % (RequestId,IsLast,str(info)))

    def OnFrontDisConnected(self, reason):
        self.logger.info('MD:front disconnected,reason:%s' % (reason,))

    def OnFrontConnected(self):
        self.logger.info('MD:front connected')
        self.user_login(self._broker_id, self._investor_id, self._passwd)

    def user_login(self, broker_id, investor_id, passwd):
        req = ustruct.ReqUserLogin(BrokerID=tob(broker_id), UserID=tob(investor_id), Password=tob(passwd))
        r=self.ReqUserLogin(req,self.inc_request_id())

    def OnRspUserLogin(self, userlogin, info, rid, is_last):
        self.logger.info('MD:user login:%s,info:%s,rid:%s,is_last:%s' % (userlogin,info,rid,is_last))
        logging.info(self._instruments)
        logging.info('is_last=%s,errorCheck:%s' % (is_last,self.checkErrorRspInfo(info)))
        if is_last and not self.checkErrorRspInfo(info):
            self.logger.info("MD:get today's trading day:%s" % repr(self.GetTradingDay()))
            self.subscribe_market_data(self._instruments)

    def subscribe_market_data(self, instruments):
        if instruments:
            self.SubscribeMarketData([tob(i) for i in instruments])

    def unsubscribe_market_data(self, instruments):
        if instruments:
            self.UnSubscribeMarketData([tob(i) for i in instruments])

    def update_instruments(self,cur_instruments):
        '''
            ����������Լ
            �˶����ټ����ĺ�Լ
        '''
        instruments_new = [ instrument for instrument in cur_instruments if instrument not in self._instruments]
        instruments_discard = [ instrument for instrument in self._instruments if instrument not in cur_instruments]
        self._instruments.update(instruments_new)    #set û�� += �������
        self.subscribe_market_data(instruments_new)
        self._instruments -= set(instruments_discard)
        self.unsubscribe_market_data(instruments_discard)
        logging.info('%s:listen to:%s' % (self._name,self._instruments))
        logging.info('%s:discard:%s' % (self._name,instruments_discard))

    def OnRtnDepthMarketData(self, depth_market_data):
        #print(depth_market_data.BidPrice1,depth_market_data.BidVolume1,depth_market_data.AskPrice1,depth_market_data.AskVolume1,depth_market_data.LastPrice,depth_market_data.Volume,depth_market_data.UpdateTime,depth_market_data.UpdateMillisec,depth_market_data.InstrumentID)
        #print('on data......\n')
        try: #��ȷ�����ﲻ���ɶ����
            dp = depth_market_data
            InstrumentID = tos(dp.InstrumentID)
            #print('thread id:',threading.current_thread().ident,dp.InstrumentID,dp.UpdateTime,dp.UpdateMillisec,dp.TradingDay) #ҹ�̵�TradeingDay���ڴ���,��updateTimeδ��
            #time.sleep(10)
            if depth_market_data.LastPrice > 999999 or depth_market_data.LastPrice < 10:
                self.logger.warning('MD:�յ���������������:%s,LastPrice=:%s' %(InstrumentID,depth_market_data.LastPrice))
            if InstrumentID not in self._instruments:
                self.logger.warning('MD:�յ�δ���ĵ�����:%s' %(InstrumentID,))
                return
            #self.logger.debug('�յ�����:%s,time=%s:%s' %(InstrumentID,depth_market_data.UpdateTime,depth_market_data.UpdateMillisec))
            #4print(InstrumentID,dp.UpdateTime,dp.UpdateMillisec)
            is_updated = self._controller.check_last(InstrumentID,tos(dp.UpdateTime),dp.UpdateMillisec,dp.Volume)
            if is_updated:
                ctick = self.market_data2tick(depth_market_data)
                if ctick:
                    if ctick.date > self._cur_day:   #����,cur_day��ȫ��tick����
                        self._cur_day = ctick.date
                    self._controller.new_tick(ctick)
            else:
                pass
        finally:
            pass
        
    def market_data2tick(self,market_data):
        """
            market_data�ĸ�ʽת��������, �������ݶ�ת��Ϊ����
            ҹ�������ڼ�¼�ϵĹ���:
                1. 0:0֮ǰ, ������ǰһ������
                2. 0:0��֮��,��������һ������
                ��ô����Ϊ�˱��� ��������һ������ʱ,���ֵĸý����� 23:59���������� 00:01���ֵ����
        """
        InstrumentID = tos(market_data.InstrumentID)
        UpdateTime = tos(market_data.UpdateTime)
        TradingDay = tos(market_data.TradingDay)
        try:
            state = '��ʼ'
            rev = base.TICK(instrument = InstrumentID,date=self._cur_day)
            rev.min1 = int(UpdateTime[:2]+UpdateTime[3:5])
            if len(TradingDay.strip()) > 0:
                rev.tdate = int(TradingDay)
            else:
                raise ValueError("�����TradingDay����,TradingDay=%s" % (TradingDay,))
            if rev.min1 >= base.NIGHT_BEGIN:
                if self._cur_day > 0:
                    rev.date = self._cur_day
                else:
                    rev.date = utils.pre_day(rev.tdate)
            else:
                rev.date = rev.tdate

            rev.sec = int(UpdateTime[-2:])
            rev.msec = int(market_data.UpdateMillisec)
            rev.holding = int(market_data.OpenInterest+0.1)
            rev.dvolume = market_data.Volume
            rev.damount = market_data.Turnover + base.EPSL
            rev.price = market_data.LastPrice + base.EPSL
            rev.high = market_data.HighestPrice + base.EPSL
            rev.low = market_data.LowestPrice + base.EPSL
            rev.time = rev.date%10000 * 1000000+ rev.min1*100 + rev.sec
            #���rev.tdate��Ϊ�˴���ҹ�����
            state = '���:low, market_data.BidPrice1=%d' % (market_data.BidPrice1,)
            rev.bid_price = market_data.BidPrice1+ base.EPSL
            state = '���:bid_price'
            rev.bid_volume = market_data.BidVolume1
            state = '���:bid_volume'
            rev.ask_price = market_data.AskPrice1 + base.EPSL
            rev.ask_volume = market_data.AskVolume1
            #self.logger.warning('MD:��������:%s' % market_data)
            if not rev.is_valid():
                raise ValueError("tick not valid")
        except Exception as inst:
            self.logger.warning('MD:��������ת������:%s,��ֵ����=%s' % (str(inst),state))
            self.logger.warning('MD:��������ת������,Դ��¼:%s' % market_data)
            self.logger.warning('MD:%s ��������ת������:%s,updateTime="%s",msec="%s",tday="%s"' % (InstrumentID,str(inst),UpdateTime,market_data.UpdateMillisec,TradingDay))
            return None
        return rev

