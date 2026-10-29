"""명시적 상태 조회/설정 검증만 제공하는 비활성 진입점."""

import sys

from . import __version__
from .runtime.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if type(args) is not list or any(type(item) is not str for item in args):
        print("QuantHarbor: invalid command.", file=sys.stderr)
        return 2
    if args == ["--version"]:
        print(f"QuantHarbor {__version__}")
        return 0
    if args == ["status"]:
        print("QuantHarbor foundation: inactive; synthetic only; external disabled.")
        return 0
    if args == ["--help"]:
        print("Usage: python -m quantharbor --version | status | validate-config PATH | report [--format text|json]")
        return 0
    if args in (["report"], ["report", "--format", "text"], ["report", "--format", "json"]):
        from .runtime.report_cli import report_cli
        return report_cli(args[-1] if len(args) == 3 else 'text')
    if len(args) == 2 and args[0] == "validate-config":
        try:
            load_settings(args[1])
        except Exception:
            # 경로·TOML 원문·예상 밖 예외 본문도 CLI 출력에 포함하지 않는다.
            print("QuantHarbor: invalid synthetic configuration.", file=sys.stderr)
            return 2
        print("QuantHarbor: synthetic configuration valid; no services started.")
        return 0
    print("QuantHarbor: invalid command.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
