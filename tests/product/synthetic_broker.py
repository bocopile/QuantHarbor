"""Q19 독립 합성 자료. 공식 예제 응답·사용자 계좌·키를 사용하지 않는다."""
from dataclasses import replace
import json

from quantharbor.adapters.synthetic_broker import FixtureTransport
from quantharbor.application.broker_read import read_broker
from quantharbor.domain.broker_read import (
    BrokerCursor, BrokerReadBinding, BrokerReadCapability, BrokerReadRequest, BrokerReadScope,
)
from quantharbor.ports.broker_read import BrokerFixturePage

START = '2026-10-24T00:00:00Z'
NOW = '2026-10-24T00:00:10Z'
DEADLINE = '2026-10-24T00:00:30Z'


def binding(**changes):
    return replace(BrokerReadBinding('broker-read-binding-v1', 'synthetic', 'kis',
        'synthetic-account:fixture', 'capability-v1', 'paper', 'kis-read-synthetic-v1', 'catalog-v1'), **changes)


def scope(op):
    if op == 'kr_balance':
        return BrokerReadScope('market_balance', 'KR', 'KRW')
    if op == 'kr_orders':
        return BrokerReadScope('cash_orders', 'KR', 'KRW', 'KRX', '2026-10-23', '2026-10-24', 'inner')
    if op == 'kr_buy_capacity':
        return BrokerReadScope('buy_capacity', 'KR', 'KRW', 'KRX', symbol='SYNTH', price='100.00', order_kind='01')
    if op == 'us_balance':
        return BrokerReadScope('market_balance', 'US', 'USD', 'NASD')
    if op == 'us_orders':
        return BrokerReadScope('broker_overseas_all', 'overseas', 'source', start_date='2026-10-23', end_date='2026-10-24')
    if op == 'us_present_balance':
        return BrokerReadScope('market_balance', 'US', 'USD')
    return BrokerReadScope('unsupported', 'unknown', 'source')


def request(op='kr_balance', **changes):
    return replace(BrokerReadRequest(1, 'synthetic', 'query-fixture', binding(), op, scope(op), START, DEADLINE), **changes)


def capability(req=None, **changes):
    req = request() if req is None else req
    return replace(BrokerReadCapability(1, 'synthetic', req.binding, req.operation, req.scope,
        'synthetic_supported' if req.operation in ('kr_balance', 'kr_orders', 'kr_buy_capacity',
        'us_balance', 'us_orders', 'us_present_balance') else 'unconfirmed', 'synthetic-evidence-v1',
        '2026-10-23T00:00:00Z', '2026-10-25T00:00:00Z'), **changes)


def holding(symbol='SYNTH', quantity='3.00'):
    return {'pdno': symbol, 'hldg_qty': quantity, 'ord_psbl_qty': '0'}


def order(quantity='3', *, overseas=False, number='order-1'):
    row = {'ord_dt': '20261024', 'ord_gno_brno': 'branch-synthetic', 'odno': number,
           'orgn_odno': 'original-synthetic', 'pdno': 'SYNTH'}
    row.update({'ft_ord_qty': '10', 'ft_ccld_qty': quantity, 'nccs_qty': '0',
                'tr_crcy_cd': 'USD', 'ovrs_excg_cd': 'NASD'} if overseas else
               {'ord_qty': '10', 'tot_ccld_qty': quantity, 'rmn_qty': '0'})
    return row


def body(op='kr_balance', *, empty=False):
    data = {'rt_cd': '0', 'msg_cd': 'SYNTHETIC', 'msg1': 'synthetic fixture only'}
    if op == 'kr_balance':
        data.update(output1=[] if empty else [holding()], output2=[] if empty else
            [{'dnca_tot_amt': '0', 'nxdy_excc_amt': '1.2300', 'prvs_rcdl_excc_amt': '2'}])
    elif op == 'kr_orders':
        data.update(output1=[] if empty else [order()], output2={
            'tot_ord_qty': '0' if empty else '10', 'tot_ccld_qty': '0' if empty else '3',
            'tot_ccld_amt': '0', 'prsm_tlex_smtl': '0', 'pchs_avg_pric': '0'})
    elif op == 'kr_buy_capacity':
        data['output'] = {} if empty else {name: '0' for name in (
            'ord_psbl_cash', 'ord_psbl_sbst', 'ruse_psbl_amt', 'fund_rpch_chgs', 'psbl_qty_calc_unpr',
            'nrcvb_buy_amt', 'nrcvb_buy_qty', 'max_buy_amt', 'max_buy_qty', 'cma_evlu_amt',
            'ovrs_re_use_amt_wcrc', 'ord_psbl_frcr_amt_wcrc')}
    elif op == 'us_balance':
        data.update(output1=[] if empty else [{'ovrs_pdno': 'SYNTH', 'tr_crcy_cd': 'USD',
            'ovrs_excg_cd': 'NASD', 'ovrs_cblc_qty': '3', 'ord_psbl_qty': '0'}], output2=[])
    elif op == 'us_orders':
        data['output'] = [] if empty else [order(overseas=True)]
    elif op == 'us_present_balance':
        data.update(output1=[] if empty else [{'pdno': 'SYNTH', 'buy_crcy_cd': 'USD',
            'ovrs_excg_cd': 'NASD', 'cblc_qty13': '3', 'ord_psbl_qty1': '0'}],
            output2=[] if empty else [{'crcy_cd': 'USD', 'frcr_dncl_amt_2': '0',
                'frcr_drwg_psbl_amt_1': '0', 'nxdy_frcr_drwg_psbl_amt': '0', 'frcr_evlu_amt2': '1'}],
            output3=[] if empty else [{'frcr_use_psbl_amt': '0'}])
    if op in ('kr_balance', 'kr_orders', 'us_balance', 'us_orders'):
        suffix = '100' if op.startswith('kr_') else '200'
        data['ctx_area_fk' + suffix] = ''
        data['ctx_area_nk' + suffix] = ''
    return data


def page(req=None, *, data=None, raw=None, index=0, cursor=None, out=None,
         marker='', terminal=True, at='2026-10-24T00:00:01Z', identity=None):
    req = request() if req is None else req
    data = body(req.operation) if data is None else data
    if out is not None:
        suffix = '100' if req.operation.startswith('kr_') else '200'
        data = data | {'ctx_area_fk' + suffix: out.forward, 'ctx_area_nk' + suffix: out.next}
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode() if raw is None else raw
    return BrokerFixturePage(req, index, BrokerCursor('', '') if cursor is None else cursor, at,
        raw, marker, 'synthetic_terminal_v1' if terminal else None, identity)


def run(pages=None, *, req=None, cap=None, now=NOW):
    req = request() if req is None else req
    cap = capability(req) if cap is None else cap
    return read_broker(req, cap, FixtureTransport((page(req),) if pages is None else pages), evaluated_at=now)
