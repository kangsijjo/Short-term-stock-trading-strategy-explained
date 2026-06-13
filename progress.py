"""공용 진행률 표시 — 오래 걸리는 배치 작업용 (퍼센트 + 게이지 + ETA).

사용:
    from progress import bar
    import time
    t0 = time.time()
    for i, item in enumerate(items, 1):
        ...
        if i % 25 == 0 or i == len(items):
            print(bar(i, len(items), t0, extra=f"저장 {n_ok} 실패 {n_fail}"))

로그 파일에도 안전하도록 \\r 갱신 대신 줄 단위 출력.
"""

import time


def bar(done, total, t0, width=20, extra=""):
    if total <= 0:
        return ""
    pct = done / total
    filled = int(width * pct)
    gauge = "█" * filled + "░" * (width - filled)
    elapsed = time.time() - t0
    eta = (elapsed / done) * (total - done) if done else 0

    def _fmt(sec):
        sec = int(sec)
        if sec >= 3600:
            return f"{sec // 3600}시간{(sec % 3600) // 60}분"
        if sec >= 60:
            return f"{sec // 60}분{sec % 60:02d}초"
        return f"{sec}초"

    s = f"[{gauge}] {pct * 100:5.1f}% ({done:,}/{total:,}) 경과 {_fmt(elapsed)} · 남은 ~{_fmt(eta)}"
    if extra:
        s += f" | {extra}"
    return s
