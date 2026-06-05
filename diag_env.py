"""'.env' 진단 스크립트 - KIS 키가 왜 config 에서 안 읽히는지 확인.

사용법:  py -3.11 diag_env.py
이 스크립트는 키 값 전체를 출력하지 않습니다 (길이 + 앞6자/뒤4자만).
"""

from pathlib import Path

KEYS = [
    "KIS_ENV",
    "KIS_PROD_APP_KEY", "KIS_PROD_APP_SECRET", "KIS_PROD_ACCOUNT",
    "KIS_MOCK_APP_KEY", "KIS_MOCK_APP_SECRET", "KIS_MOCK_ACCOUNT",
]


def mask(k, val):
    if val is None:
        return "<키 자체가 없음 (dotenv 가 이 줄을 인식 못 함)>"
    if any(s in k for s in ("KEY", "SECRET")):
        return f"len={len(val)} first6={val[:6]!r} last4={val[-4:]!r}"
    return repr(val)


def main():
    print("=" * 64)
    env_path = Path(".env")
    if not env_path.exists():
        print(f"[ERROR] .env 파일이 현재 폴더에 없습니다: {env_path.resolve()}")
        return

    raw = env_path.read_bytes()
    # f-string expression 안에 백슬래시를 못 쓰므로(3.11) 미리 변수로 계산
    bom = b"\xef\xbb\xbf"
    crlf_count = raw.count(b"\r\n")
    lf_count = raw.count(b"\n")
    has_bom = raw.startswith(bom)
    print(f".env 경로 : {env_path.resolve()}")
    print(f"크기      : {len(raw)} bytes")
    print(f"첫 3바이트: {raw[:3]!r}  (BOM 여부: {has_bom})")
    print(f"줄바꿈    : CRLF={crlf_count}개, LF총={lf_count}개")

    # ---- dotenv 파서가 실제로 읽은 값 ----
    print("-" * 64)
    print("[dotenv_values 가 .env 에서 추출한 값]")
    try:
        from dotenv import dotenv_values
        v = dotenv_values(".env")
        for k in KEYS:
            print(f"  {k:22s}: {mask(k, v.get(k))}")
    except ImportError:
        print("  [ERROR] python-dotenv 미설치 → py -3.11 -m pip install python-dotenv")
        return

    # ---- 문제 줄 raw 출력 (특수문자/공백 그대로 보임) ----
    print("-" * 64)
    print("[KIS_PROD / KIS_MOCK APP_KEY 줄 raw repr]")
    text = env_path.read_text(encoding="utf-8-sig")
    for i, line in enumerate(text.splitlines(), 1):
        if "APP_KEY" in line or "APP_SECRET" in line:
            # 값 부분은 마스킹
            if "=" in line:
                key_part, _, val_part = line.partition("=")
                shown = f"{key_part}={val_part[:6]}...({len(val_part)}자)"
            else:
                shown = line
            print(f"  line {i}: {shown!r}")
    print("=" * 64)
    print("판정 가이드:")
    print(" - dotenv 값이 <키 자체가 없음> → 그 윗줄이 따옴표/줄바꿈으로 깨졌을 가능성")
    print(" - line raw 에 앞쪽 공백, 탭, 'KEY =' 처럼 = 주변 공백이 보이면 그게 원인")
    print(" - 값에 # 가 있고 그 앞에 공백이 있으면 dotenv 가 주석으로 자름")


if __name__ == "__main__":
    main()