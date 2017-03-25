# -*- coding:gbk -*-
"""
        deprecated, ֱ��ʹ��TraderSpiDelegate + trader_api_stub
        Mock TraderSPI, �ṩͳһ��׮λ, ���Բ���TradeCommandQueue�Ƿ���ȷ
        ����֤�ϲ�����Ƿ���ȷ,ֻ�ṩͨ��

"""
import logging
from datetime import datetime

from ctp.futures import ApiStruct as UType

from ..trader import trade_command
from ..common.base import (BaseObject,
                           LONG,SHORT,
                           XCLOSE,XCLOSE_TODAY,
            )
from ..common.contract_type import CM_ALL as call
from ..trader.position import ORDER_STATUS


class TraderSpiStub(object):
    logger = logging.getLogger('ctp.TraderSpiStub')

    def __init__(self,available,margin=0,frozen_margin=0):
        self._trade_command_queue = None
        self._available = available  #���ý��
        self._margin = margin        #��֤��
        self._frozen_margin = frozen_margin
        #self._macro_command_queue = macro_command_queue
        #����������
        self.reset_login_info()
        #order_ref => command ��ӳ��, �����ڻص��л�ȡ�����Ϣ
        self._ref_map = {}
        self._first_login_time = 0
        self._infos = []
        self._exchange_id = "EX_STUB"
        self._cur_order_sys_id = 10000

    @property
    def broker(self):
        return self._broker

    @property
    def investor(self):
        return self._investor

    @property
    def balance(self):
        return self._available + self._margin + self._frozen_margin

    @property
    def front_id(self):
        return self._login_info.front_id

    @property
    def session_id(self):
        return self._login_info.session_id

    @property
    def queue(self):
        #return self._trade_command_queue
        raise TypeError("��֧�ֶ�ȡTraderSpiDelegate��trade_command_queue")

    @queue.setter
    def queue(self,queue):
        self._trade_command_queue = queue

    @property
    def trading_day(self):
        return self._login_info.trading_day

    @trading_day.setter
    def trading_day(self,trading_day):
        self._login_info.trading_day = trading_day

    def inc_order_sys_id(self):
        self._cur_order_sys_id += 1
        return self._cur_order_sys_id

    def reset_login_info(self):
        self._login_info = BaseObject(front_id="FRONT_STUB", session_id='SS_STUB', order_ref=0,
                                      trading_day=datetime.today().strftime("%Y%m%d"),
                                      is_logged = False, is_settlement_info_confirmed = False
                )

    def inc_request_id(self):
        self._login_info.order_ref += 1
        return self._login_info.order_ref

    #def delay_command(self, command, delta):
    #    self.macro_command_queue.put_command(DelayedCommand(command, delta))

    def day_finalize(self):
        self.reset_login_info()

    #�ظ�״̬����

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
        ref_id = self.inc_request_id()
        self.logger.info('TD:trader to login, issued')
        self._trade_command_queue.on_login_success(datetime.today().strftime("%Y%m%d"))
        return 0


    def query_settlement_info(self):
        #�������ڱ�ʾȡ��һ����㵥, ������Ӧ������ȷ��
        self.logger.info('TD:ȡ��һ�ս��㵥��Ϣ��ȷ��, BrokerID=%s, investorID=%s' % (self.broker, self.investor))
        #time.sleep(1)   #��������, ��Ϊ��ʱticksδ���Ѿ���ʼ����, �ʲ�����macro_command_queue��ʽ. ������Ϊ���ٲ�ѯ���㵥�Ƿ���ȷ��, �����Ѿ�û����������
        ref_id = self.inc_request_id()
        self._trade_command_queue.put_command(trade_command.SETTLEMENT_CONFIRM_COMMAND)
        return 0

    def confirm_settlement_info(self):
        self.logger.info('TD-CSI:׼��ȷ�Ͻ��㵥')
        ref_id = self.inc_request_id()
        self._trade_command_queue.on_settlement_info_confirmed()
        return 0

    #����׼��
    #��ȡ�ʻ��ʽ�
    def fetch_trading_account(self):
        #��ȡ�ʽ��ʻ�
        logging.info('A:��ȡ�ʽ��ʻ�..')
        ref_id = self.inc_request_id()
        self._trade_command_queue.on_query_trading_account(ref_id, self.get_balance(), self._available, self._margin, self._frozen_margin)
        return 0,ref_id


    # ��ȡ�ֲ�
    def fetch_investor_position(self, instrument_id):
        #��ȡ��Լ�ĵ�ǰ�ֲ�
        logging.info('A:��ȡ��Լ%s�ĵ�ǰ�ֲ�..' % (instrument_id, ))
        ref_id = self.inc_request_id()
        #logging.info('A:��ѯ�ֲ�, ������������ֵ:%s' % rP)
        return 0,ref_id

    # ��ȡ�ֲ���ϸ
    def fetch_investor_position_detail(self, instrument_id):
        """
            ��ȡ��Լ�ĵ�ǰ�ֲ���ϸ��Ŀǰû��
        """
        logging.info('A:��ȡ��Լ%s�ĵ�ǰ�ֲ�..' % (instrument_id, ))
        ref_id = self.inc_request_id()
        #logging.info('A:��ѯ�ֲ�, ������������ֵ:%s' % r)
        return 0,ref_id

    #��ȡ��Լ��֤����
    def fetch_instrument_marginrate(self, instrument_id):
        """
            ��֤���ʶ��趨Ϊ0.1
        """
        ref_id = self.inc_request_id()
        self._trade_command_queue.on_query_instrument_marginrate(instrument_id, 0.1, 0.1)
        return 0

    #��ѯ��Լ��Ϣ
    def fetch_instrument(self, instrument_id):
        ref_id = self.inc_request_id()
        ctype = call.cname2ctype(instrument_id)
        self._trade_command_queue.on_query_instrument(instrument_id,
                                                         ctype.exchange_name,
                                                         ctype.unit,
                                                         ctype.multiplier,
                                                         0.1,
                                                         0.1,
                                                    )
        return 0


    #��ȡ������Ϣ, Ŀ�����ڻ�ȡ�����ǵ�ͣ�۸�
    def fetch_depth_market_data(self, instrument_id):
        ref_id = self.inc_request_id()
        self._trade_command_queue.on_query_market_data(instrument_id,
                                                          self._trading_day,
                                                          99999999,
                                                          0,
                                                         )
        return 0

    #���ײ���
    #����
    def r2uid(self,trading_day,exchange_id,order_sys_id):
        uid = "%s:%s:%s" % (trading_day,exchange_id,order_sys_id)

    def get_ctp_direction(self,direction):
        #print(direction)
        return UType.D_Buy if direction == LONG else UType.D_Sell

    def xopen(self, instrument_id, direction, volume,price):
        #print("xopen",instrument_id,volume,price)
        order_sys_id = self.inc_order_sys_id()
        uid = self.r2uid(self._trading_day,self._exchange_id,order_sys_id)
        trade_info = BaseObject(front_id=self._login_info.front_id,
                                session_id=self.get_session_id(),
                                trading_day=self._trading_day,
                                exchange_id=self._exchange_id,
                                order_sys_id=order_sys_id
                    )

        ctype = call.cname2ctype()
        self._trade_command_queue.on_accept(instrument_id, direction, volume, price,uid,trade_info)
        #print("xopen",instrument_id,volume,price)
        self._trade_command_queue.on_rtn_order(uid,ORDER_STATUS.SUCCESSED,volume)
        trade_time = datetime.now().strftime("%H%M%S")
        self._trade_command_queue.on_trade(uid,self._trading_day,trade_time,volume,price)
        return 0

    def xclose(self, instrument_id, close_type,direction, volume,price):
        """
            ����������ƽ���ƽ��
                �㷴�Ļ��ͻᱻCTPֱ�Ӿܾ�. ��ƽ����ƽ���ղ�,�����㹻���,�ͻᱨ:�ۺϽ���ƽ̨��ƽ���λ����
        """
        order_sys_id = self.inc_order_sys_id()
        uid = self.r2uid(self._trading_day,self._exchange_id,order_sys_id)
        trade_info = BaseObject(front_id=self._login_info.front_id,
                                session_id=self.get_session_id(),
                                trading_day=self._trading_day,
                                exchange_id=self._exchange_id,
                                order_sys_id=order_sys_id
                    )

        self._trade_command_queue.on_accept(instrument_id, direction, volume, price,uid,trade_info)
        self._trade_command_queue.on_rtn_order(uid,ORDER_STATUS.SUCCESSED,volume)
        trade_time = datetime.now().strftime("%H%M%S")
        self._trade_command_queue.on_trade(uid,self._trading_day,trade_time,volume,price)
        return 0

    def xcancel(self,instrument_id,exchange_id,order_sys_id,front_id,session_id,order_ref):
        """
            Mock�в������κ�Ч��
        """
        self.logger.info('SPI_XC:ȡ������')
        ref_id = self.inc_request_id()
        #orderActionRef��һ�����п��޵�ֵ,���ô���Ҳ�޹ؽ�Ҫ
        return 0

