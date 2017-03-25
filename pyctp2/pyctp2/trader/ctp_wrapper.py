#-*- coding:gbk -*-

import logging
import threading

from ctp.futures import TraderApi
from ctp.futures import ApiStruct as UStruct
from ctp.futures import ApiStruct as UType

from ..common.base import (BaseObject,
                           LONG,
                           XCLOSE_TODAY,
                           STATE_PATH,
                        )
from ..common.errors import TradeError
from . import trade_command
from ..trader.position import ORDER_STATUS



class TraderSpiDelegate(TraderApi):
    """
        ����������Ӧת����Agent
        �����д�������
        SPI�ص�����������Ҫ�ٴε���TradeApi, ������ͨ��trade_command_queue, ��ʵ��ͳһ��ں�ͬ��
    """
    logger = logging.getLogger('ctp.TraderSpiDelegate')
    def __init__(self,
            broker,
            investor,
            passwd,
        ):
        self._trade_command_queue = None
        #self.macro_command_queue = macro_command_queue
        #����������
        self._broker = broker
        self._investor = investor
        self._passwd = passwd
        self.reset_login_info()
        #order_ref => command ��ӳ��, �����ڻص��л�ȡ�����Ϣ
        self._ref_map = {}
        self._first_login_time = 0
        self._infos = []
        self._uids = set()
        self._lock = threading.Lock()
        #self.log_fname = STATE_PATH + "/trade.log"

    @property
    def broker(self):
        return self._broker

    @property
    def investor(self):
        return self._investor

    @property
    def front_id(self):
        return self.login_info.front_id

    @property
    def session_id(self):
        return self.login_info.session_id

    @property
    def queue(self):
        #return self._trade_command_queue
        raise TypeError("��֧�ֶ�ȡTraderSpiDelegate��trade_command_queue")

    @queue.setter
    def queue(self,queue):
        self._trade_command_queue = queue

    def reset_login_info(self):
        self.login_info = BaseObject(front_id='', session_id='', order_ref=0, trading_day=0, is_logged = False, is_settlement_info_confirmed = False)

    def inc_request_id(self):
        with self._lock:
            self.login_info.order_ref += 1
            return self.login_info.order_ref

    def peep_next_request_id(self): #�����ڲ���stub�ķ���
        return self.login_info.order_ref + 1

    #def delay_command(self, command, delta):
    #    self.macro_command_queue.put_command(DelayedCommand(command, delta))

    def r2uid(self,trading_day,exchange_id,order_sys_id):
        uid = "%s:%s:%s" % (trading_day,exchange_id,order_sys_id)
        return uid
        #print("CW:uid:",uid)

    def day_finalize(self):
        self.reset_login_info()

    #�ظ�״̬����
    def isRspSuccess(self, RspInfo):
        return RspInfo == None or RspInfo.ErrorID == 0

    def resp_common(self, rsp_info, bIsLast, name='Ĭ��'):
        #self.logger.debug("resp: %s" % str(rsp_info))
        if not self.isRspSuccess(rsp_info):
            self.logger.info("TD:%sʧ��" % name)
            return -1
        elif bIsLast and self.isRspSuccess(rsp_info):
            self.logger.info("TD:%s�ɹ�" % name)
            return 1
        else:
            self.logger.info("TD:%s���: �ȴ����ݽ�����ȫ..." % name)
            return 0

    def OnRspError(self, info, RequestId, IsLast):
        """ ����Ӧ��
        """
        self.logger.error('TD:requestID:%s, IsLast:%s, info:%s' % (RequestId, IsLast, str(info)))

    ##���׳�ʼ��
    #��½,ȷ�Ͻ��㵥
    def OnFrontConnected(self):
        """
            ���ͻ����뽻�׺�̨������ͨ������ʱ����δ��¼ǰ�����÷��������á�
        """
        self.logger.info('TD:trader front connected')
        self._trade_command_queue.put_command(trade_command.LOGIN_COMMAND)

    def OnFrontDisconnected(self, nReason):
        self.logger.info('TD:trader front disconnected, reason=%s' % (nReason, ))

    def user_login(self):
        self.logger.info('TD:trader to login')
        req = UStruct.ReqUserLogin(BrokerID=self._broker, UserID=self._investor, Password=self._passwd)
        ref_id = self.inc_request_id()
        ret = self.ReqUserLogin(req, ref_id)
        self.logger.info('TD:trader to login, issued')
        return ret

    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        self.logger.info("TD:on trader login:%s" % str(pRspUserLogin))
        self.logger.debug("TD:loggin %s" % str(pRspInfo))
        if not self.isRspSuccess(pRspInfo):
            self.logger.warning('TD:trader login failed, errMsg=%s' %(pRspInfo.ErrorMsg, ))
            print('�ۺϽ���ƽ̨��½ʧ�ܣ�����������û���/����')
            self.login_info.is_logged = False
            return
        self.login_info.is_logged = True
        if self._first_login_time == 0:
            self._first_login_time = pRspUserLogin.LoginTime     #�� HH:MM:SS��ʽ,���� hh:mm:ss��ʽ? ����ָ��ǰ��0
        self.logger.info('TD:trader login success')
        self._login_success(pRspUserLogin.FrontID, pRspUserLogin.SessionID, pRspUserLogin.MaxOrderRef, pRspUserLogin.TradingDay)
        self._trade_command_queue.on_login_success(pRspUserLogin.TradingDay)
        #self.trade_command_queue.put_command(trade_command.SETTLEMENT_QUERY_COMMAND)

    def _login_success(self, frontID, sessionID, max_order_ref, trading_day):
        self.login_info.front_id = frontID
        self.login_info.session_id = sessionID
        self.login_info.order_ref = int(max_order_ref) + 10000
        self.login_info.trading_day = trading_day

    def OnRspUserLogout(self, pUserLogout, pRspInfo, nRequestID, bIsLast):
        """�ǳ�������Ӧ"""
        self.logger.info('TD:trader logout')
        self.login_info.is_logged = False

    def query_settlement_info(self):
        #�������ڱ�ʾȡ��һ����㵥, ������Ӧ������ȷ��
        self.logger.info('TD:ȡ��һ�ս��㵥��Ϣ��ȷ��, BrokerID=%s, investorID=%s' % (self._broker, self._investor))
        req = UStruct.QrySettlementInfo(BrokerID=self._broker, InvestorID=self._investor, TradingDay='')
        #time.sleep(1)   #��������, ��Ϊ��ʱticksδ���Ѿ���ʼ����, �ʲ�����macro_command_queue��ʽ. ������Ϊ���ٲ�ѯ���㵥�Ƿ���ȷ��, �����Ѿ�û����������
        ref_id = self.inc_request_id()
        ret = self.ReqQrySettlementInfo(req, ref_id)
        return ret

    def OnRspQrySettlementInfo(self, pSettlementInfo, pRspInfo, nRequestID, bIsLast):
        """�����ѯͶ���߽�����Ϣ��Ӧ
            ��������Ϣ���зֳɼ���,���з�λ�����ð�һ�������п�,�п��ܻ���ִ���
        """
        #print('Rsp ���㵥��ѯ')
        if(self.resp_common(pRspInfo, bIsLast, '���㵥��ѯ')>0):
            self.logger.info('���㵥��ѯ���, ׼��ȷ��')
            try:
                self.logger.info('TD:���㵥����:%s' % pSettlementInfo.Content)
            except Exception as inst:
                self.logger.warning('TD-ORQSI-A ���㵥���ݴ���:%s' % str(inst))
            #self.trade_command_queue.on_query_settlement_info(pSettlementInfo)     #���ﲻ����������, û��Ҫ
            self._trade_command_queue.put_command(trade_command.SETTLEMENT_CONFIRM_COMMAND)
        else:  #������δ��ɷ�֧, ��Ҫֱ�Ӻ���
            try:
                self.logger.info('TD:���㵥������...:%s' % pSettlementInfo.Content)
            except Exception as inst:
                self.logger.warning('TD-ORQSI-B ���㵥���ݴ���:%s' % str(inst))

    def confirm_settlement_info(self):
        self.logger.info('TD-CSI:׼��ȷ�Ͻ��㵥')
        req = UStruct.SettlementInfoConfirm(BrokerID=self._broker, InvestorID=self._investor)
        ref_id = self.inc_request_id()
        ret = self.ReqSettlementInfoConfirm(req, ref_id)
        return ret

    def OnRspSettlementInfoConfirm(self, pSettlementInfoConfirm, pRspInfo, nRequestID, bIsLast):
        """Ͷ���߽�����ȷ����Ӧ"""
        if(self.resp_common(pRspInfo, bIsLast, '���㵥ȷ��')>0):
            self.login_info.is_settlement_info_confirmed = True
            self.logger.info('TD:���㵥ȷ��ʱ��: %s-%s' %(pSettlementInfoConfirm.ConfirmDate, pSettlementInfoConfirm.ConfirmTime))
            self._trade_command_queue.on_settlement_info_confirmed()

    #����׼��
    #��ȡ�ʻ��ʽ�
    def fetch_trading_account(self):
        #��ȡ�ʽ��ʻ�
        logging.info('A:��ȡ�ʽ��ʻ�..')
        req = UStruct.QryTradingAccount(BrokerID=self._broker, InvestorID=self._investor)
        ref_id = self.inc_request_id()
        ret = self.ReqQryTradingAccount(req,  ref_id)
        return ret,ref_id
        #logging.info('A:��ѯ�ʽ��˻�, ������������ֵ:%s' % r)

    def OnRspQryTradingAccount(self, pTradingAccount, pRspInfo, nRequestID, bIsLast):
        """
            �����ѯ�ʽ��˻���Ӧ
        """
        self.logger.info('TD:�ʽ��˻���Ӧ:%s' % pTradingAccount)
        if bIsLast and self.isRspSuccess(pRspInfo):
            pTA = pTradingAccount
            self._trade_command_queue.on_query_trading_account(nRequestID, pTA.Balance, pTA.Available, pTA.CurrMargin, pTA.FrozenMargin)
        else:
            #logging
            pass

    # ��ȡ�ֲ�
    def fetch_investor_position(self, instrument_id):
        #��ȡ��Լ�ĵ�ǰ�ֲ�
        logging.info('A:��ȡ��Լ%s�ĵ�ǰ�ֲ�..' % (instrument_id, ))
        req = UStruct.QryInvestorPosition(BrokerID=self._broker, InvestorID=self._investor, InstrumentID=instrument_id)
        ref_id = self.inc_request_id()
        ret = self.ReqQryInvestorPosition(req, self.ref_id)
        #logging.info('A:��ѯ�ֲ�, ������������ֵ:%s' % rP)
        return ret,ref_id

    def OnRspQryInvestorPosition(self, pInvestorPosition, pRspInfo, nRequestID, bIsLast):
        """�����ѯͶ���ֲ߳���Ӧ"""
        #print '��ѯ�ֲ���Ӧ', str(pInvestorPosition), str(pRspInfo)
        if self.isRspSuccess(pRspInfo): #ÿ��һ�����������ݱ�
            pass
        else:
            #logging
            pass

    # ��ȡ�ֲ���ϸ
    def fetch_investor_position_detail(self, instrument_id):
        """
            ��ȡ��Լ�ĵ�ǰ�ֲ���ϸ��Ŀǰû��
        """
        logging.info('A:��ȡ��Լ%s�ĵ�ǰ�ֲ�..' % (instrument_id, ))
        req = UStruct.QryInvestorPositionDetail(BrokerID=self._broker, InvestorID=self._investor, InstrumentID=instrument_id)
        ref_id = self.inc_request_id()
        ret = self.ReqQryInvestorPositionDetail(req,  self.ref_id)
        #logging.info('A:��ѯ�ֲ�, ������������ֵ:%s' % r)
        return ret,ref_id

    def OnRspQryInvestorPositionDetail(self, pInvestorPositionDetail, pRspInfo, nRequestID, bIsLast):
        """�����ѯͶ���ֲ߳���ϸ��Ӧ"""
        logging.info(str(pInvestorPositionDetail))
        if self.isRspSuccess(pRspInfo): #ÿ��һ�����������ݱ�
            pass
        else:
            #logging
            pass

    #��ȡ��Լ��֤����
    def fetch_instrument_marginrate(self, instrument_id):
        req = UStruct.QryInstrumentMarginRate(BrokerID=self._broker,
                        InvestorID = self._investor,
                        InstrumentID=instrument_id,
                        HedgeFlag = UType.HF_Speculation
                )
        ref_id = self.inc_request_id()
        ret= self.ReqQryInstrumentMarginRate(req, self.inc_request_id())
        logging.info('A:��ѯ��֤����, ������������ֵ:%s' % ret)
        return ret

    def OnRspQryInstrumentMarginRate(self, pInstrumentMarginRate, pRspInfo, nRequestID, bIsLast):
        """
            ��֤���ʻر������صı�Ȼ�Ǿ���ֵ
            ���ﷵ�ص��ǵ�����(���������ݳֲ������������)�ı�֤����
        """
        self._infos.append(pInstrumentMarginRate)
        if not pInstrumentMarginRate:   # Ҳ�����pInstrumentMarginRate��pRspInfo��ΪNone�������,����ѯ�����ڵĺ�Լʱ
            return
        if bIsLast and self.isRspSuccess(pRspInfo):
            pIMR = pInstrumentMarginRate
            self._trade_command_queue.on_query_instrument_marginrate(pIMR.InstrumentID, pIMR.LongMarginRatioByMoney, pIMR.ShortMarginRatioByMoney)
        else:
            #logging
            pass

    #��ѯ��Լ��Ϣ
    def fetch_instrument(self, instrument_id):
        req = UStruct.QryInstrument(
                        InstrumentID=instrument_id,
                )
        ref_id = self.inc_request_id()
        ret = self.ReqQryInstrument(req, self.inc_request_id())
        logging.info('A:��ѯ��Լ, ������������ֵ:%s' % ret)
        return ret

    def OnRspQryInstrument(self, pInstrument, pRspInfo, nRequestID, bIsLast):
        """
            ��Լ�ر���
            ���ﷵ�ص���ԭʼ��֤����,����û��ʵ���ô�
        """
        self._infos.append(pInstrument)
        self.logger.info("CT_ORQI_1:%s" % pInstrument)
        self.logger.info("CT_ORQI_2:%s" % pRspInfo)
        #��Ȼ���ܷ��� pInstrument��pRespInfo��ΪNone,���״̬����!!
        if not pInstrument:
            return
        if bIsLast and self.isRspSuccess(pRspInfo):
            self._trade_command_queue.on_query_instrument(pInstrument.InstrumentID,
                                                         pInstrument.ExchangeID,
                                                         pInstrument.PriceTick,
                                                         pInstrument.VolumeMultiple,
                                                         pInstrument.LongMarginRatio,
                                                         pInstrument.ShortMarginRatio,
                                                    )
            #print pInstrument
        else:#ģ����ѯ�Ľ��, ����˶����Լ�����ݣ�ֻ�����һ����bLast��True
            self._trade_command_queue.on_query_instrument(pInstrument.InstrumentID,
                                                         pInstrument.ExchangeID,
                                                         pInstrument.PriceTick,
                                                         pInstrument.VolumeMultiple,
                                                         pInstrument.LongMarginRatio,
                                                         pInstrument.ShortMarginRatio,
                                                    )

    def OnRtnInstrumentStatus(self, pInstrumentStatus):
        #pInstrumentStatus.InstrumentID �� Ʒ������
        self.logger.info("CWR:ORIS:{id},{time},{status}".format(id=pInstrumentStatus.InstrumentID,time=pInstrumentStatus.EnterTime,status=pInstrumentStatus.InstrumentStatus))
        status = int(pInstrumentStatus.InstrumentStatus)
        #is_on_trading = True if status  == '2' or status =='3' else False
        #self._trade_command_queue.on_instrument_status(pInstrumentStatus.InstrumentID,pInstrumentStatus.EnterTime,is_on_trading)
        self._trade_command_queue.on_instrument_status(pInstrumentStatus.InstrumentID,pInstrumentStatus.EnterTime,status)

    #��ȡ������Ϣ, Ŀ�����ڻ�ȡ�����ǵ�ͣ�۸�
    def fetch_depth_market_data(self, instrument_id):
        ref_id = self.inc_request_id()
        req = UStruct.QryDepthMarketData(InstrumentID = instrument_id)
        ret = self.ReqQryDepthMarketData(req, ref_id)
        logging.info('A:��ѯ��Լ����, ������������ֵ:%s' % ret)
        return ret

    def OnRspQryDepthMarketData(self, pDepthMarketData, pRspInfo, nRequestID, bIsLast):
        """�����ѯ������Ӧ
           һ��ֻ��ѯһ����Լ��, ��һ�γɹ�, isLast=1
        """
        self.logger.info('TD:��ѯ������Ӧ:%s' % pDepthMarketData)
        if bIsLast and self.isRspSuccess(pRspInfo):
            pDMD = pDepthMarketData
            self._trade_command_queue.on_query_market_data(pDMD.InstrumentID,
                                                          int(pDMD.TradingDay),
                                                          pDMD.UpperLimitPrice,
                                                          pDMD.LowerLimitPrice
                                                         )
        else: #��Ӧ�ó���
            logging.error('Error on query market data:%s' % (pDepthMarketData.InstrumentID, ))
            pass

    #���ײ���
    #����

    def to_ctp_direction(self,direction):
        #print(direction)
        return UType.D_Buy if direction == LONG else UType.D_Sell

    def from_ctp_direction(self,ctp_direction):
        return LONG if ctp_direction == UType.D_Buy else UType.D_Sell

    def xopen(self, instrument_id, direction, volume, price):
        #print("spidelegate,xopen",instrument_id,volume,price,self)
        ref_id = self.inc_request_id()
        req = UStruct.InputOrder(
                InstrumentID = instrument_id,
                Direction = self.to_ctp_direction(direction),
                OrderRef = str(ref_id),
                LimitPrice = price,    #�и����ʣ�double������α�֤����������ڷ�������ȡ��?
                VolumeTotalOriginal = volume,
                OrderPriceType = UType.OPT_LimitPrice,
                ContingentCondition = UType.CC_Immediately,

                BrokerID = self._broker,
                InvestorID = self._investor,
                CombOffsetFlag = UType.OF_Open,          #���� 5λ�ַ�, ����ֻ�õ���0λ
                CombHedgeFlag = UType.HF_Speculation,    #Ͷ�� 5λ�ַ�, ����ֻ�õ���0λ

                VolumeCondition = UType.VC_AV,
                MinVolume = 1,   #��������е㲻ȷ��, �е��ĵ����0��
                ForceCloseReason = UType.FCC_NotForceClose,
                IsAutoSuspend = 1,
                UserForceClose = 0,
                TimeCondition = UType.TC_GFD,
            )
        ret = self.ReqOrderInsert(req, ref_id)
        return ret

    def xclose(self, instrument_id, close_type,direction, volume,price):
        """
            ����������ƽ���ƽ��
                �㷴�Ļ��ͻᱻCTPֱ�Ӿܾ�. ��ƽ����ƽ���ղ�,�����㹻���,�ͻᱨ:�ۺϽ���ƽ̨��ƽ���λ����
        """
        ref_id = self.inc_request_id()
        close_flag = UType.OF_CloseToday if close_type == XCLOSE_TODAY else UType.OF_Close
        req = UStruct.InputOrder(
                InstrumentID = instrument_id,
                Direction = self.to_ctp_direction(direction),
                OrderRef = str(ref_id),
                LimitPrice = price,    #�и����ʣ�double������α�֤����������ڷ�������ȡ��?
                VolumeTotalOriginal = volume,
                OrderPriceType = UType.OPT_LimitPrice,

                BrokerID = self._broker,
                InvestorID = self._investor,
                CombOffsetFlag = close_flag,
                CombHedgeFlag = UType.HF_Speculation,    #Ͷ�� 5λ�ַ�, ����ֻ�õ���0λ

                VolumeCondition = UType.VC_AV,
                MinVolume = 1,   #��������е㲻ȷ��, �е��ĵ����0��
                ForceCloseReason = UType.FCC_NotForceClose,
                IsAutoSuspend = 1,
                UserForceClose = 0,
                TimeCondition = UType.TC_GFD,
            )
        ret = self.ReqOrderInsert(req, ref_id)
        return ret

    def OnRspOrderInsert(self, pInputOrder, pRspInfo, nRequestID, bIsLast):
        """
            ����δͨ������У��, ��CTP�ܾ�
            ���������Ӧ�ó���
            Ϊ���ɻָ��Ĵ���,ֻ�����ڵ����ڼ�
        """
        #print('ERROR Order Insert,CTP Reject')
        self.logger.error('TD:CTP����¼�����ر�, ������Ӧ�ó���, rspInfo=%s'%(str(pRspInfo), ))
        #self.trade_command_queue.on_rtn_order(pInputOrder.OrderRef,ORDER_STATUS.LOCAL_REJECT)
        self._trade_command_queue.on_reject(pInputOrder.InstrumentID,
                                           self.from_ctp_direction(pInputOrder.Direction),
                                           pInputOrder.VolumeTotalOriginal,
                                           pInputOrder.LimitPrice,
                                           pRspInfo.ErrorID,
                                    )


    def OnErrRtnOrderInsert(self, pInputOrder, pRspInfo):
        """
            ����������¼�����ر�
            ���������Ӧ�ó���
            Ϊ���ɻָ��Ĵ���,ֻ�����ڵ����ڼ�
        """
        #print('ERROR Order Insert,Exchange Reject')
        self.logger.error('TD:����������¼�����ر�, ������Ӧ�ó���, rspInfo=%s'%(str(pRspInfo), ))
        self.logger.error('%s:%s:%s:%s',pInputOrder.OrderRef, pInputOrder.InstrumentID, pRspInfo.ErrorID, pRspInfo.ErrorMsg)
        #self.trade_command_queue.on_rtn_order(pInputOrder.OrderRef,ORDER_STATUS.EXCHANGE_REJECT)
        self._trade_command_queue.on_reject(pInputOrder.InstrumentID,
                                           self.from_ctp_direction(pInputOrder.Direction),
                                           pInputOrder.VolumeTotalOriginal,
                                           pInputOrder.LimitPrice,
                                           pRspInfo.ErrorID,
                                    )


    def _check_accepted(self, pOrder):
        uid = self.r2uid(pOrder.TradingDay, pOrder.ExchangeID, pOrder.OrderSysID)
        #print("CW:uid=",uid)
        #print("CW:check_accepted:",uid,pOrder.TradingDay, pOrder.ExchangeID, pOrder.OrderSysID)
        if uid in self._uids:
            return uid
        trade_info = BaseObject(front_id=pOrder.FrontID, session_id=pOrder.SessionID, trading_day=int(pOrder.TradingDay),
                                exchange_id=pOrder.ExchangeID, order_sys_id=pOrder.OrderSysID,
                                order_ref = pOrder.OrderRef,
                    )
        self._trade_command_queue.on_accept(pOrder.InstrumentID,
                                           self.from_ctp_direction(pOrder.Direction),
                                           pOrder.VolumeTotalOriginal,
                                           pOrder.LimitPrice,
                                           uid,
                                           trade_info,
        )
        self._uids.add(uid)
        return uid

    def OnRtnOrder(self, pOrder):
        """ ����֪ͨ
            CTP�����������ܱ���
        """
        self._infos.append(pOrder)
        #print("ORO:direction",pOrder.Direction)
        #self.logger.info('������Ӧ repr, Order=%s' % repr(pOrder))
        #print("ORO:",pOrder.ExchangeID)
        self.logger.info('������Ӧ str, Order=%s' % str(pOrder))
        if pOrder.FrontID == self.login_info.front_id and pOrder.SessionID != self.login_info.session_id:
            self.logger.info("�յ���½ǰ��ί�лر�,%s,%s",self.login_info.front_id,self.login_info.session_id)
            #self.trade_command_queue.on_pre_rtn_order(pOrder.FrontID,pOrder.SessionID,pOrder.OrderRef,pOrder.InstrumentID,pOrder.InsertTime,pOrder.VolumeTotal,pOrder.VolumeTraded)
            pass
        elif pOrder.OrderSubmitStatus == UType.OSS_InsertRejected:
            ##���1: ��ҹ��ʱ����δ��ҹ�̽��׵�Ʒ�ֵı��� #�����ύ״̬:�����Ѿ����ܾ� #״̬��Ϣ:�ѳ����������ܾ�DCE:��Ʒ�ֵ�ǰ�ǳ�ʼ����!#����״̬:����
            ##���2: ��ͣ����ʱ���µ�:  #�����ύ״̬:�����Ѿ����ܾ� #״̬��Ϣ:�ѳ����������ܾ�DCE:��Ʒ�ֵ�ǰ�ǿ�����ͣ! #����״̬:����:
            ##���3: ���к��µ�(15:00/15:15֮��) #�����ύ״̬:�����Ѿ����ܾ�#״̬��Ϣ:�ѳ����������ܾ�DCE:��Ʒ�ֵ�ǰ�Ǳ���! #����״̬:����
            ##��ʱ,���յ� #״̬��Ϣ:�������ύ ��RtnOrder,���յ� �������ܾ��� RtnOrder,����˵�յ�����RtnOrder
            #   ctp.TraderSpiDelegate:OnRtnOrder:493:2014-08-25 13:26:07,602 INFO ������Ӧ str, Order=<��������:20140825,֣�����ɽ�����:0,��������:��,�����ύ״̬:�Ѿ��ύ,�Ự���:-943256868,��С�ɽ���:1,����:1,����ʱ��:,ֹ���:0.0,ί��ʱ��:13:27:09,���͹�˾�������:7866,��ɽ�����:0,��Լ�ڽ������Ĵ���:m1501,������:1,����ʱ��:,GTD����:,��������:10040,��������:����,�ɽ�������:�κ�����,��������:����,���ر������:         693,������ʾ���:0,��ر���:,�����۸�����:�޼�,����ʱ��:,ʣ������:1,״̬��Ϣ:�������ύ,��װ���:2,ǿƽԭ��:��ǿƽ,��Լ����:m1501,ǰ�ñ��:2,�û�ǿ����־:0,����״̬:δ֪,����������:DCE,�������:,������:0,�Զ������־:1,��������־:0,���:0,��Ͽ�ƽ��־:0,������Դ:���Բ�����,������:20140825,�����Ա���:,��Ч������:������Ч,����޸�ʱ��:,�û��˲�Ʒ��Ϣ:,�۸�:3401.0,���Ͷ���ױ���־:1>
            #   ctp.TraderSpiDelegate:OnRtnOrder:512:2014-08-25 13:26:07,602 INFO TD:CTP����Order����δ����������
            #   ctp.TraderSpiDelegate:OnRtnOrder:493:2014-08-25 13:26:07,641 INFO ������Ӧ str, Order=<��������:20140825,֣�����ɽ�����:0,��������:��,�����ύ״̬:�����Ѿ����ܾ�,�Ự���:-943256868,��С�ɽ���:1,����:1,����ʱ��:,ֹ���:0.0,ί��ʱ��:13:27:09,���͹�˾�������:7866,��ɽ�����:0,��Լ�ڽ������Ĵ���:m1501,������:1,����ʱ��:,GTD����:,��������:10040,��������:����,�ɽ�������:�κ�����,��������:����,���ر������:         693,������ʾ���:1,��ر���:,�����۸�����:�޼�,����ʱ��:,ʣ������:1,״̬��Ϣ:�ѳ����������ܾ�DCE:��Ʒ�ֵ�ǰ�ǿ�����ͣ!,��װ���:2,ǿƽԭ��:��ǿƽ,��Լ����:m1501,ǰ�ñ��:2,�û�ǿ����־:0,����״̬:����,����������:DCE,�������:,������:0,�Զ������־:1,��������־:0,���:0,��Ͽ�ƽ��־:0,������Դ:���Բ�����,������:20140825��Ч������:������Ч,����޸�ʱ��:,�û��˲�Ʒ��Ϣ:,�۸�:3401.0,���Ͷ���ױ���־:1>
            #   ctp.TraderSpiDelegate:OnRtnOrder:501:2014-08-25 13:26:07,641 INFO RTN_REJECT:�������ܾ�
            self.logger.info("RTN_REJECT:�������ܾ�")
            self._trade_command_queue.on_reject(pOrder.InstrumentID,
                                               self.from_ctp_direction(pOrder.Direction),
                                               pOrder.VolumeTotalOriginal,
                                               pOrder.LimitPrice,
                                               #-1,   #û�о���ԭ��ľܾ�
                                               TradeError.TIME_ERROR,
                                            )
        elif pOrder.OrderStatus == UType.OST_Unknown and pOrder.OrderSysID== '' :
            #CTP���ܣ���δ����������  pOrder.OrderSubmitStatus == UType.OSS_InsertSubmitted.  δ��!!!.�ɽ�ʱҲ�����ύ״̬
            #print 'CTP����Order����δ����������, BrokerID=%s, BrokerOrderSeq = %s, TraderID=%s, OrderLocalID=%s' % (pOrder.BrokerID, pOrder.BrokerOrderSeq, pOrder.TraderID, pOrder.OrderLocalID)
            self.logger.info('TD:CTP����Order����δ����������, BrokerID=%s, BrokerOrderSeq = %s, TraderID=%s, OrderLocalID=%s' % (pOrder.BrokerID, pOrder.BrokerOrderSeq, pOrder.TraderID, pOrder.OrderLocalID))
            #print('TD:CTP����Order����δ����������, BrokerID=%s, BrokerOrderSeq = %s, TraderID=%s, OrderLocalID=%s' % (pOrder.BrokerID, pOrder.BrokerOrderSeq, pOrder.TraderID, pOrder.OrderLocalID))
            #self._check_accepted(pOrder)   #exchange_idδ�趨
        elif pOrder.OrderStatus == UType.OST_Unknown and pOrder.OrderSysID != '':     #���������ܺ�,�õ�OrderSysID
            #print '����������Order, exchangeID=%s, OrderSysID=%s, TraderID=%s, OrderLocalID=%s' % (pOrder.ExchangeID, pOrder.OrderSysID, pOrder.TraderID, pOrder.OrderLocalID)
            self.logger.info('TD:����������Order, exchangeID=%s, OrderSysID=%s, TraderID=%s, OrderLocalID=%s' % (pOrder.ExchangeID, pOrder.OrderSysID, pOrder.TraderID, pOrder.OrderLocalID))
            self._check_accepted(pOrder)
        elif pOrder.OrderStatus == UType.OST_PartTradedNotQueueing:
            uid = self._check_accepted(pOrder)    #�������ڸ���ԭ����δ���ֵ�����Exchange Accept��Ӧ
            #print("ORO:VT:",pOrder.VolumeTraded)
            self._trade_command_queue.on_rtn_order(uid,ORDER_STATUS.PART_SUCCESSED,pOrder.VolumeTraded)
        elif pOrder.OrderStatus == UType.OST_AllTraded:
            uid = self._check_accepted(pOrder)    #�������ڸ���ԭ����δ���ֵ�����Exchange Accept��Ӧ
            self._trade_command_queue.on_rtn_order(uid,ORDER_STATUS.SUCCESSED,pOrder.VolumeTraded)
        elif pOrder.OrderStatus == UType.OST_Canceled or pOrder.OrderStatus == UType.OST_NoTradeNotQueueing:
            uid = self._check_accepted(pOrder)    #�������ڸ���ԭ����δ���ֵ�����Exchange Accept��Ӧ
            self._trade_command_queue.on_rtn_order(uid,ORDER_STATUS.CANCELLED,pOrder.VolumeTraded)

    def OnRtnTrade(self, pTrade):
        """
            �ɽ�֪ͨ
        """
        self.logger.info("SPI_OT:�յ��ɽ��ر� %s",str(pTrade))
        #print("SPI_OT:",pTrade.ExchangeID)
        #if pTrade.TradeTime < self.first_login_time:       #�������յ���½ǰ�ĳɽ��ر�,ֻ���յ�ί�лر�
        #    self.logger.info("�յ���½ǰ�ĳɽ��ر�",str(pTrade))
        #    self.trade_command_queue.on_pre_trade(pTrade.ExchangeID,pTrade.OrderSysID,pTrade.TradeTime,pTrade.InstrumentId,pTrade.Volume,pTrade.Price)
        #else:
        self.logger.info("�յ��ɽ��ر�:%s",str(pTrade))
        self.logger.info('SPI_TD:�ɽ�֪ͨ, BrokerID=%s, BrokerOrderSeq = %s, exchangeID=%s, OrderSysID=%s, TraderID=%s, OrderLocalID=%s' %(pTrade.BrokerID, pTrade.BrokerOrderSeq, pTrade.ExchangeID, pTrade.OrderSysID, pTrade.TraderID, pTrade.OrderLocalID))
        uid = self.r2uid(pTrade.TradingDay, pTrade.ExchangeID, pTrade.OrderSysID)   #��Ȼ֮ǰ�Ѿ�����OnRtnOrder�ĵ���
        self._trade_command_queue.on_trade(uid,int(pTrade.TradeDate),pTrade.TradeTime,pTrade.Volume,pTrade.Price)

    def xcancel(self,instrument_id,exchange_id,order_sys_id,front_id,session_id,order_ref):
        """
            ����RESTART��ʽ������ʱ,���յ�֮ǰ��ί��/�ɽ��ر�. ��ί�лر���,�и�ί�е�״̬
                ���������ʱ�����ݶԲ��Ϻ�,�ͻ��� �����Ҳ�����Ӧ���� �Ĵ���
            �������󷵻ص�OnRtnOrder�Ǳ����������pOrder��ί����Ӧ��״̬����,�����е����ĳ���OnRtnOrder
                ��OnRtnOrder��, front_id,session_id�ȶ���Ӧ���������Ǹ�pOrder
                ��������µ�½,��ô����������������session_id��OnRtnOrder��Ӧ�е�session_id�ǲ�һ����
        """
        self.logger.info('SPI_XC:ȡ������')
        ref_id = self.inc_request_id()
        #orderActionRef��һ�����п��޵�ֵ,���ô���Ҳ�޹ؽ�Ҫ
        req = UStruct.InputOrderAction(
                InstrumentID = instrument_id,
                BrokerID = self._broker,
                InvestorID = self._investor,
                ActionFlag = UType.AF_Delete,
                OrderActionRef = ref_id,    #   ����Ҫһ��int,��TMì��, OrderRef��һ��String
                #OrderActionRef = order_ref, #   ���ref�޹ؽ�Ҫ,�����ĵ�,Ӧ����ref_id
            )
        if exchange_id:   #������,�����Exchange_id+orderSysID��ʽ. �����ַ�ʽ���ɳ��������ⵥ
            req.ExchangeID = exchange_id
            req.OrderSysID = order_sys_id
        else:   #����frontID + sessionID + orderRef��ʶ�ķ�ʽ. �����ַ�ʽ���ɳ��������ⵥ
            #�����֧�Ĳ��� ������OnRtnOrder��һ��Callbackʱ���ܴ���. ��Ҫ�ڸûص��в���
            req.FrontID = front_id
            req.SessionID = session_id
            req.OrderRef = str(order_ref)
        ret= self.ReqOrderAction(req,self.inc_request_id())
        return ret

    def OnRspOrderAction(self, pInputOrderAction, pRspInfo, nRequestID, bIsLast):
        """
            ctp����У�����
        """
        self.logger.warning('TD:CTP����¼�����ر�, ������Ӧ�ó���, rspInfo=%s'%(str(pRspInfo), ))
        #self.trade_command_queue.on_rtn_order(pInputOrderAction.OrderRef,ORDER_STATUS.LOCAL_REJECT)

    def OnErrRtnOrderAction(self, pOrderAction, pRspInfo):
        """
            ������������������ر�
        """
        #print("in CTP_WRAPPER:OEROA")
        self.logger.warning('TD:����������¼�����ر�, �����Ѿ��ɽ�, rspInfo=%s'%(str(pRspInfo), ))
        #self.trade_command_queue.on_rtn_order(pOrderAction.OrderRef,ORDER_STATUS.EXCHANGE_REJECT)


