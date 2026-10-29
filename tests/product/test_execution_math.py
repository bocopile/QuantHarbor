"""고정 golden의 순수 계산 검증. 실제 DB 증거와 구분한다."""
from dataclasses import replace
from fractions import Fraction
import unittest

from quantharbor.domain import execution as d
from quantharbor.domain.execution_math import (cash_with_reservations,sellable,one_sided,turnover,prospective_loss)
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.target import CashCalculation
from synthetic_execution import AT,MANIFEST


def reserve(component,bound,held,used='0',settled='0'):
    return d.ReservationSlice('reservation-'+component,'intent-1','obligation-'+component,component,'cash','USD',
        AT,'2024-03-09T00:00:00Z',bound,held,used,'0','0',settled,AT,())


class ExecutionMathTests(unittest.TestCase):
    def test_EX06_EX07_EX08_independent_literal_A598_at_each_boundary(self):
        base=CashCalculation('USD','1000','0','100','1000','0','0','900','0','900')
        principal=reserve('principal','300','200','100')
        cost=reserve('cost','2','2')
        row=cash_with_reservations(base,(principal,cost))
        self.assertEqual((row.ledger,row.outstanding,row.floor,row.broker,row.unreflected,row.debits,row.available),
                         ('1000','302','100','1000','202','100','598'))
        base=replace(base,ledger_cash='900',available='800',remaining='800')
        principal=replace(principal,settled='100')
        row=cash_with_reservations(base,(principal,cost))
        self.assertEqual((row.ledger,row.outstanding,row.broker,row.unreflected,row.debits,row.available),('900','202','1000','202','100','598'))
        row=cash_with_reservations(base,(principal,cost),broker_amount='900',included=('obligation-principal:used',))
        self.assertEqual((row.ledger,row.outstanding,row.broker,row.unreflected,row.debits,row.available),('900','202','900','202','0','598'))
        self.assertEqual(cost.held,'2')

    def test_EX38_obligations_800_then302_then402_remaining96(self):
        base=CashCalculation('USD','1000','100','100','950','50','0','800','0','800')
        self.assertEqual(cash_with_reservations(base,()).available,'800')
        r=reserve('principal','302','302')
        self.assertEqual(cash_with_reservations(base,(r,)).available,'498')
        other=replace(r,reservation_id='other',obligation_id='other',bound='402',held='402')
        self.assertEqual(cash_with_reservations(base,(r,other)).available,'96')

    def test_EX03_600_cannot_fund_302_and402(self):
        base=CashCalculation('USD','1000','0','400','1000','0','0','600','0','600')
        self.assertEqual(cash_with_reservations(base,()).available,'600')
        self.assertEqual(cash_with_reservations(base,(reserve('principal','302','302'),)).available,'298')
        self.assertEqual(cash_with_reservations(base,(reserve('principal','402','402'),)).available,'198')

    def test_EX09_sellable7_reject8(self):
        self.assertEqual(sellable('12','4','10','2','1'),'7')
        self.assertGreater(Fraction(8),Fraction(sellable('12','4','10','2','1')))

    def test_EX10_postquery_credit_and_unsettled_receivable_not_added(self):
        base=CashCalculation('USD','1000','0','100','500','0','0','500','0','500')
        self.assertEqual(cash_with_reservations(base,()).available,'500')
        # A settled local credit can increase L; independent unchanged B remains the cap.
        self.assertEqual(cash_with_reservations(replace(base,ledger_cash='1500'),()).available,'500')

    def test_EX11_one_sided_buys_never_netted_against_sales(self):
        self.assertEqual(one_sided('400','150','100'),('300','550'))
        self.assertGreater(Fraction('550'),Fraction('500'))

    def test_EX12_time_weighted_nav_turnover105percent(self):
        self.assertEqual(turnover('400','350','300','1000'),Fraction('1.05'))
        self.assertGreater(turnover('400','350','300','1000'),1)
        for nav in (None,'0','-1'):
            with self.assertRaises(d.ExecutionDenied): turnover('400','350','300',nav)

    def test_EX13_worst_loss55_and_unknown_performance_denied(self):
        loss,dd=prospective_loss('40','15','1000','0.02')
        self.assertEqual(loss,55)
        self.assertEqual(dd,Fraction('0.035'))
        for values in ((None,'15','1000','0.02'),('40','15',None,'0.02'),('40','15','0','0.02')):
            with self.assertRaises(d.ExecutionDenied): prospective_loss(*values)

    def test_EX39_component_conservation_exact_and_negative_boundaries(self):
        r=reserve('principal','300','200','100')
        for changes in ({'held':'201'},{'used':'-1'},{'bound':300},{'released':'0.1'}):
            with self.subTest(changes=changes),self.assertRaises(ContractError): replace(r,**changes)
        with self.assertRaises(d.ExecutionDenied):
            cash_with_reservations(CashCalculation('USD','1000','0','0','1000','0','0','1000','0','1000'),(replace(r,settled='101'),))

    def test_EX37_negative_available_is_not_clamped_to_zero(self):
        base=CashCalculation('USD','100','50','100','100','50','0','-50','0','-50')
        self.assertEqual(cash_with_reservations(base,()).available,'-50')

    def test_fixed40_and_storage_root_budget_literals(self):
        self.assertEqual(tuple(x['id'] for x in MANIFEST['cases']),tuple('EX%02d'%i for i in range(1,41)))
        limits=MANIFEST['limits']
        self.assertEqual((limits['execution_records'],limits['execution_bytes']),(1024,67108864))
        self.assertEqual((limits['intent_reserved_records'],limits['intent_reserved_bytes']),(384,25165824))
