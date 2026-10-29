"""단일 원통화·기초수량0 이동평균 원가. 원천 비용 배분은 builder가 확인한다."""
from quantharbor.domain.research import CostBasisResult, basis_math


def calculate_basis(account_ref, position, currency, quantum, facts, closing_native_value, *,
                    opening_quantity='0', supported=True):
    return CostBasisResult(1, 'synthetic', account_ref, position, currency, quantum, facts,
        opening_quantity, closing_native_value, supported,
        *basis_math(facts, opening_quantity, closing_native_value, quantum, supported))
