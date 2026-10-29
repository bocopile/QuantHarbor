"""Q22 bounded canonical stdin → 로컬 stdout. 파일·환경·네트워크 경로 없음."""
import sys

from quantharbor.application.reporting import render_report
from quantharbor.domain.reporting import ReportPresentationRequest
from quantharbor.domain.serialization import parse_payload

MAX_INPUT_BYTES = 65536


def report_cli(output_format):
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if not raw or len(raw) > MAX_INPUT_BYTES:
            raise ValueError()
        request = parse_payload(raw)
        if request.schema_name != 'ReportPresentationRequest' or type(request.payload) is not ReportPresentationRequest:
            raise ValueError()
        rendered = render_report(request.payload, output_format=output_format)
    except Exception:
        print('QuantHarbor: invalid synthetic report input.', file=sys.stderr)
        return 2
    sys.stdout.write(rendered)
    return 0
