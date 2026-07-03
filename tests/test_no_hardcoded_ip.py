"""
検証ゲート（Checker）: ソース中にハードコードされたIPアドレスが無いことを保証する。
ローカル実行: pytest tests/test_no_hardcoded_ip.py -v
いまは check_alerts.py にIP直書きがある想定なので、このテストは「赤」で始まる。
その赤をループ（Maker）が緑に変えにいき、緑化後は恒久的なリグレッション関所として残る。
"""
import re
import pathlib
import pytest

TARGET_FILES = ["scripts/check_alerts.py"]
ALLOWLIST = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _is_valid_ipv4(token: str) -> bool:
    return all(0 <= int(octet) <= 255 for octet in token.split("."))


def _find_hardcoded_ips(path: pathlib.Path):
    hits = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for token in _IPV4.findall(line):
            if _is_valid_ipv4(token) and token not in ALLOWLIST:
                hits.append((lineno, token, line.strip()))
    return hits


@pytest.mark.parametrize("filename", TARGET_FILES)
def test_no_hardcoded_ip(filename):
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / filename
    assert path.exists(), f"監視対象が見つからない: {path}"
    hits = _find_hardcoded_ips(path)
    if hits:
        detail = "\n".join(f"  {filename}:{ln}  {ip}  |  {src}" for ln, ip, src in hits)
        pytest.fail(f"ハードコードされたIPを検出（設定/DNS名へ外出しすること）:\n{detail}")
