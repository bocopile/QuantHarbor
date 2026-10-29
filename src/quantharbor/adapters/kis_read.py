"""공식 고정 KIS 명세의 비전송 계획과 합성 source 관측 decoder.

근거: cd63caee6aeb90553d506b15ab6866cfad23beda의 6종 function/chk.
필드 이름·shape만 사용한다. vendor 실행 코드/인증/host/HTTP 기능은 없다.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType

from quantharbor.domain.broker_read import (
    BrokerCursor, BrokerObservation, BrokerReadRequest, SourceNumber, SUPPORTED, exact, numeric_fields,
)
from quantharbor.domain.primitives import ContractError, calendar_date, identifier
from quantharbor.ports.broker_read import BrokerFixturePage


@dataclass(frozen=True, slots=True)
class SectionSpec:
    name: str
    shapes: tuple[str, ...]
    kind: str
    identity: tuple[str, ...]
    numbers: tuple[str, ...]
    unused: tuple[str, ...]

    @property
    def allowed(self):
        return frozenset(self.identity + self.numbers + self.unused)


# Exact source field names, including the chk's mixed-case domestic exchange key.
# Label ambiguity is not interpreted: all numeric semantics remain source_only/unknown.
KR_HOLDING = SectionSpec('output1', ('list',), 'holding', ('pdno',),
    numeric_fields('kr_balance', 'output1'), tuple('prdt_name trad_dvsn_name bfdy_buy_qty bfdy_sll_qty thdt_buyqty thdt_sll_qty pchs_avg_pric pchs_amt prpr evlu_amt evlu_pfls_amt evlu_pfls_rt evlu_erng_rt loan_dt loan_amt stln_slng_chgs expd_dt fltt_rt bfdy_cprs_icdc item_mgna_rt_name grta_rt_name sbst_pric stck_loan_unpr'.split()))
KR_CASH = SectionSpec('output2', ('list',), 'cash', (),
    numeric_fields('kr_balance', 'output2'), tuple('cma_evlu_amt bfdy_buy_amt thdt_buy_amt nxdy_auto_rdpt_amt bfdy_sll_amt thdt_sll_amt d2_auto_rdpt_amt bfdy_tlex_amt thdt_tlex_amt tot_loan_amt scts_evlu_amt tot_evlu_amt nass_amt fncg_gld_auto_rdpt_yn pchs_amt_smtl_amt evlu_amt_smtl_amt evlu_pfls_smtl_amt tot_stln_slng_chgs bfdy_tot_asst_evlu_amt asst_icdc_amt asst_icdc_erng_rt'.split()))
KR_ORDER = SectionSpec('output1', ('list',), 'order_cumulative',
    ('ord_dt', 'ord_gno_brno', 'odno', 'orgn_odno', 'pdno'),
    numeric_fields('kr_orders', 'output1'), tuple('ord_dvsn_name sll_buy_dvsn_cd sll_buy_dvsn_cd_name prdt_name ord_unpr ord_tmd avg_prvs cncl_yn tot_ccld_amt loan_dt ordr_empno ord_dvsn_cd cnc_cfrm_qty rjct_qty ccld_cndt_name inqr_ip_addr cpbc_ordp_ord_rcit_dvsn_cd cpbc_ordp_infm_mthd_dvsn_cd infm_tmd ctac_tlno prdt_type_cd excg_dvsn_cd cpbc_ordp_mtrl_dvsn_cd ord_orgno rsvn_ord_end_dt excg_id_dvsn_Cd stpm_cndt_pric stpm_efct_occr_dtmd'.split()))
KR_ORDER_SUMMARY = SectionSpec('output2', ('object',), 'cash', (),
    numeric_fields('kr_orders', 'output2'), ())
KR_CAPACITY = SectionSpec('output', ('object',), 'buy_capacity', (),
    numeric_fields('kr_buy_capacity', 'output'), ())
US_HOLDING = SectionSpec('output1', ('list', 'object'), 'holding',
    ('ovrs_pdno', 'tr_crcy_cd', 'ovrs_excg_cd'), numeric_fields('us_balance', 'output1'),
    tuple('cano acnt_prdt_cd prdt_type_cd frcr_evlu_pfls_amt evlu_pfls_rt pchs_avg_pric frcr_pchs_amt1 ovrs_stck_evlu_amt now_pric2 loan_type_cd loan_dt expd_dt'.split()))
US_CASH = SectionSpec('output2', ('list', 'object'), 'cash', (),
    numeric_fields('us_balance', 'output2'), ())
US_ORDER = SectionSpec('output', ('list', 'object'), 'order_cumulative',
    ('ord_dt', 'ord_gno_brno', 'odno', 'orgn_odno', 'pdno', 'tr_crcy_cd', 'ovrs_excg_cd'),
    numeric_fields('us_orders', 'output'), tuple('sll_buy_dvsn_cd sll_buy_dvsn_cd_name rvse_cncl_dvsn rvse_cncl_dvsn_name prdt_name ft_ord_unpr3 ft_ccld_unpr3 ft_ccld_amt3 prcs_stat_name rjct_rson rjct_rson_name ord_tmd tr_mket_name tr_natn tr_natn_name dmst_ord_dt thco_ord_tmd loan_type_cd loan_dt mdia_dvsn_name usa_amk_exts_rqst_yn splt_buy_attr_name'.split()))
US_PRESENT_HOLDING = SectionSpec('output1', ('list', 'object'), 'holding',
    ('pdno', 'buy_crcy_cd', 'ovrs_excg_cd'), numeric_fields('us_present_balance', 'output1'),
    tuple('thdt_buy_ccld_qty1 thdt_sll_ccld_qty1 ccld_qty_smtl1 frcr_pchs_amt frcr_evlu_amt2 evlu_pfls_amt2 evlu_pfls_rt1 bass_exrt ovrs_now_pric1 avg_unpr3 tr_mket_name natn_kor_name pchs_rmnd_wcrc_amt thdt_buy_ccld_frcr_amt thdt_sll_ccld_frcr_amt unit_amt std_pdno prdt_type_cd loan_rmnd loan_dt loan_expd_dt item_lnkg_excg_cd'.split()))
US_PRESENT_CASH = SectionSpec('output2', ('list', 'object'), 'cash', ('crcy_cd',),
    numeric_fields('us_present_balance', 'output2'),
    tuple('frcr_buy_amt_smtl frcr_sll_amt_smtl frst_bltn_exrt frcr_buy_mgn_amt frcr_etc_mgna acpl_cstd_crcy_yn'.split()))
US_PRESENT_SUMMARY = SectionSpec('output3', ('list', 'object'), 'cash', (),
    numeric_fields('us_present_balance', 'output3'), tuple('pchs_amt_smtl evlu_amt_smtl evlu_pfls_amt_smtl dncl_amt cma_evlu_amt tot_dncl_amt etc_mgna wdrw_psbl_tot_amt frcr_evlu_tota evlu_erng_rt1 pchs_amt_smtl_amt evlu_amt_smtl_amt tot_evlu_pfls_amt tot_asst_amt buy_mgn_amt mgna_tota ustl_sll_amt_smtl ustl_buy_amt_smtl tot_frcr_cblc_smtl tot_loan_amt'.split()))
SECTIONS = MappingProxyType({
    'kr_balance': (KR_HOLDING, KR_CASH), 'kr_orders': (KR_ORDER, KR_ORDER_SUMMARY),
    'kr_buy_capacity': (KR_CAPACITY,), 'us_balance': (US_HOLDING, US_CASH),
    'us_orders': (US_ORDER,),
    'us_present_balance': (US_PRESENT_HOLDING, US_PRESENT_CASH, US_PRESENT_SUMMARY),
})
PATHS = MappingProxyType({
    'kr_balance': '/uapi/domestic-stock/v1/trading/inquire-balance',
    'kr_orders': '/uapi/domestic-stock/v1/trading/inquire-daily-ccld',
    'kr_buy_capacity': '/uapi/domestic-stock/v1/trading/inquire-psbl-order',
    'us_balance': '/uapi/overseas-stock/v1/trading/inquire-balance',
    'us_orders': '/uapi/overseas-stock/v1/trading/inquire-ccnl',
    'us_present_balance': '/uapi/overseas-stock/v1/trading/inquire-present-balance',
})
TR_IDS = MappingProxyType({'kr_balance': 'VTTC8434R', 'kr_buy_capacity': 'VTTC8908R',
    'us_balance': 'VTTS3012R', 'us_orders': 'VTTS3035R', 'us_present_balance': 'VTRP6504R'})


@dataclass(frozen=True, slots=True)
class WirePlan:
    """입력은 typed request/cursor뿐. host/auth 및 임의 params 슬롯이 없다."""
    request: BrokerReadRequest
    cursor: BrokerCursor = BrokerCursor('', '')

    def __post_init__(self):
        exact(self.request, BrokerReadRequest)
        exact(self.cursor, BrokerCursor)
        if self.request.operation not in SUPPORTED:
            raise ContractError()
        if self.cursor.forward and self.request.operation in ('kr_buy_capacity', 'us_present_balance'):
            raise ContractError()

    @property
    def method(self):
        return 'GET'

    @property
    def path(self):
        return PATHS[self.request.operation]

    @property
    def tr_id(self):
        if self.request.operation == 'kr_orders':
            return 'VTTC0081R' if self.request.scope.period_class == 'inner' else 'VTSC9215R'
        return TR_IDS[self.request.operation]

    @property
    def tr_cont(self):
        return 'N' if self.cursor.forward else ''

    @property
    def params(self):
        # These are inert symbolic slots, never resolved by this module.
        params = {'CANO': '<private-binding:cano>', 'ACNT_PRDT_CD': '<private-binding:product>'}
        op, scope = self.request.operation, self.request.scope
        if op == 'kr_balance':
            params.update(AFHR_FLPR_YN='N', OFL_YN='', INQR_DVSN='02', UNPR_DVSN='01',
                FUND_STTL_ICLD_YN='N', FNCG_AMT_AUTO_RDPT_YN='N', PRCS_DVSN='00')
        elif op == 'kr_orders':
            params.update(INQR_STRT_DT=scope.start_date.replace('-', ''), INQR_END_DT=scope.end_date.replace('-', ''),
                SLL_BUY_DVSN_CD='00', PDNO='', CCLD_DVSN='00', INQR_DVSN='01', INQR_DVSN_3='01',
                ORD_GNO_BRNO='', ODNO='', INQR_DVSN_1='', EXCG_ID_DVSN_CD='KRX')
        elif op == 'kr_buy_capacity':
            params.update(PDNO=scope.symbol, ORD_UNPR=scope.price, ORD_DVSN='01',
                CMA_EVLU_AMT_ICLD_YN='N', OVRS_ICLD_YN='N')
        elif op == 'us_balance':
            params.update(OVRS_EXCG_CD=scope.exchange, TR_CRCY_CD='USD')
        elif op == 'us_orders':
            params.update(PDNO='', ORD_STRT_DT=scope.start_date.replace('-', ''), ORD_END_DT=scope.end_date.replace('-', ''),
                SLL_BUY_DVSN='00', CCLD_NCCS_DVSN='00', OVRS_EXCG_CD='', SORT_SQN='DS',
                ORD_DT='', ORD_GNO_BRNO='', ODNO='')
        else:
            params.update(WCRC_FRCR_DVSN_CD='02', NATN_CD='840', TR_MKET_CD='00', INQR_DVSN_CD='01')
        suffix = '100' if op in ('kr_balance', 'kr_orders') else '200' if op in ('us_balance', 'us_orders') else None
        if suffix:
            params['CTX_AREA_FK' + suffix] = self.cursor.forward
            params['CTX_AREA_NK' + suffix] = self.cursor.next
        return tuple(sorted(params.items()))


class DecodeError(ContractError):
    """고정 코드만 노출하며 원문·echo·msg1을 보유하지 않는다."""
    def __init__(self, reason='schema_mismatch', received_rows=0):
        super().__init__()
        self.reason = reason
        self.received_rows = received_rows


@dataclass(frozen=True, slots=True)
class DecodedPage:
    items: tuple[BrokerObservation, ...]
    response_cursor: BrokerCursor | None
    body_sha256: str
    received_bytes: int
    received_rows: int
    account_evidence: str
    reasons: tuple[str, ...]


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DecodeError()
        result[key] = value
    return result


def _reject_number(value):
    raise DecodeError()


def _bounded_tree(value, depth=0):
    if depth > 4:
        raise DecodeError()
    if type(value) is str:
        if len(value) > 512 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise DecodeError()
    elif value is None:
        return
    elif type(value) is dict:
        if len(value) > 100:
            raise DecodeError()
        for key, item in value.items():
            _bounded_tree(key, depth + 1)
            _bounded_tree(item, depth + 1)
    elif type(value) is list:
        if len(value) > 32:
            raise DecodeError('row_limit', len(value))
        for item in value:
            _bounded_tree(item, depth + 1)
    else:
        raise DecodeError()


def _source_number(row, name):
    value = row.get(name)
    missing = 'absent' if name not in row else 'null' if value is None else 'empty' if value == '' else None
    return SourceNumber(name, None if missing else value, missing, None, None,
                        'unknown' if name in ('tot_ccld_amt', 'frcr_evlu_amt2') else 'source_only')


def _identity(row, name):
    value = row.get(name)
    if value in (None, ''):
        return None
    return identifier(value)


def _observation(request, spec, row, index, received_at):
    reasons = []
    if set(row) - spec.allowed or any(name not in row for name in spec.identity):
        raise DecodeError()
    if any(type(v) not in (str, type(None)) for v in row.values()):
        raise DecodeError()
    numbers = tuple(_source_number(row, name) for name in spec.numbers
                    if name != 'frcr_evlu_amt2' or name in row)
    if any(x.value is None for x in numbers) or any(row.get(name) in (None, '') for name in spec.identity):
        reasons.append('missing_fact')
    symbol = _identity(row, 'ovrs_pdno' if request.operation == 'us_balance' else 'pdno')
    if request.operation == 'kr_buy_capacity':
        symbol = request.scope.symbol
    currency = 'KRW' if request.operation.startswith('kr_') else None
    source_currency = row.get('tr_crcy_cd', row.get('buy_crcy_cd', row.get('crcy_cd')))
    if source_currency not in (None, ''):
        if source_currency not in ('KRW', 'USD'):
            raise DecodeError()
        currency = source_currency
    venue = 'KRX' if request.operation.startswith('kr_') else _identity(row, 'ovrs_excg_cd')
    if request.operation in ('us_balance', 'us_present_balance'):
        if source_currency not in (None, '', 'USD') or venue is not None and venue not in ('NASD', 'NYSE', 'AMEX'):
            raise DecodeError()
        if request.operation == 'us_balance' and venue is not None and venue != request.scope.exchange:
            raise DecodeError()
    order_date = branch = number = original = None
    if spec.kind == 'order_cumulative':
        raw_date = row.get('ord_dt')
        if raw_date not in (None, ''):
            if len(raw_date) != 8 or not raw_date.isascii() or not raw_date.isdigit():
                raise DecodeError()
            order_date = calendar_date(raw_date[:4] + '-' + raw_date[4:6] + '-' + raw_date[6:])
            if not request.scope.start_date <= order_date <= request.scope.end_date:
                raise DecodeError()
        branch, number, original = (_identity(row, name) for name in ('ord_gno_brno', 'odno', 'orgn_odno'))
        key_material = (order_date, branch, number)
    else:
        key_material = (spec.name, symbol, venue, currency, index)
    row_key = sha256(json.dumps(key_material, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return BrokerObservation(request.query_id, request.binding, request.operation, request.scope,
        spec.kind, spec.name, row_key, symbol, venue, currency, received_at, numbers,
        order_date, branch, number, original,
        execution_granularity='order_cumulative' if spec.kind == 'order_cumulative' else 'not_applicable'), tuple(reasons)


def decode_page(page: BrokerFixturePage) -> DecodedPage:
    """순수 wire 해석. 빈 tr_cont도 실제 종료 증거로 해석하지 않는다.

    expected_identity 부재 때 echo를 검증 성공으로 승격하지 않는다.
    계좌 숫자는 비교 후 폐기하며 반환형/예외에 원문을 복사하지 않는다.
    """
    try:
        exact(page, BrokerFixturePage)
        if len(page.raw_body) > 65536:
            raise DecodeError('byte_limit')
        request = page.request
        WirePlan(request, page.request_cursor)
        body = json.loads(page.raw_body.decode('utf-8'), object_pairs_hook=_pairs,
            parse_int=_reject_number, parse_float=_reject_number, parse_constant=_reject_number)
        _bounded_tree(body)
        if type(body) is not dict:
            raise DecodeError()
        specs = SECTIONS[request.operation]
        suffix = '100' if request.operation in ('kr_balance', 'kr_orders') else '200' if request.operation in ('us_balance', 'us_orders') else None
        cursor_keys = ('ctx_area_fk' + suffix, 'ctx_area_nk' + suffix) if suffix else ()
        allowed = {'rt_cd', 'msg_cd', 'msg1'} | {s.name for s in specs} | set(cursor_keys)
        if body.keys() - allowed or 'rt_cd' not in body:
            raise DecodeError()
        if body['rt_cd'] != '0':
            raise DecodeError('source_error')
        if any(s.name not in body for s in specs):
            raise DecodeError()
        rows = []
        for spec in specs:
            section = body[spec.name]
            shape = 'list' if type(section) is list else 'object' if type(section) is dict else None
            if shape not in spec.shapes:
                raise DecodeError()
            section_rows = section if type(section) is list else [section]
            for row in section_rows:
                if type(row) is not dict:
                    raise DecodeError()
                rows.append((spec, row))
        if len(rows) > 32:
            raise DecodeError('row_limit', len(rows))
        response_cursor = None
        if suffix:
            if any(name not in body or type(body[name]) is not str for name in cursor_keys):
                raise DecodeError('cursor_missing')
            response_cursor = BrokerCursor(*(body[name] for name in cursor_keys))
        items, reasons = [], []
        echo_seen = False
        for index, (spec, row) in enumerate(rows):
            echo = ('cano' in row, 'acnt_prdt_cd' in row)
            if any(echo):
                if not all(echo):
                    raise DecodeError('account_mismatch')
                echo_seen = True
                if page.expected_identity is None:
                    reasons.append('account_unverified')
                elif (row['cano'], row['acnt_prdt_cd']) != ('00000000', '00'):
                    raise DecodeError('account_mismatch')
            item, missing = _observation(request, spec, row, index, page.received_at)
            items.append(item)
            reasons.extend(missing)
        evidence = 'synthetic_echo_verified' if echo_seen and page.expected_identity is not None else 'unverified' if echo_seen else 'request_bound_only'
        return DecodedPage(tuple(items), response_cursor, sha256(page.raw_body).hexdigest(),
            len(page.raw_body), len(rows), evidence, tuple(dict.fromkeys(reasons)))
    except DecodeError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError, KeyError, AttributeError):
        raise DecodeError() from None
