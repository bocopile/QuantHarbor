"""정확 산식의 공개 조립 함수. 원천 검증은 application builder 책임이다."""
from quantharbor.domain.research import PerformanceResult, performance_math


def calculate_performance(points, flows, traded_notional, benchmark_return):
    return PerformanceResult(1, 'synthetic', points, flows, traded_notional, benchmark_return,
        *performance_math(points, flows, traded_notional, benchmark_return))
