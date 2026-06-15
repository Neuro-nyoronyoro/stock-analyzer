from datetime import datetime, timedelta
from config import SCORE_WEIGHTS

CACHE_TTL_HOURS = 24


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def score_dividend(info: dict) -> float:
    """配当スコア（0〜100）"""
    score = 0.0
    dy = info.get("dividend_yield")
    pr = info.get("payout_ratio")

    if dy is None:
        return 30.0

    dy_pct = dy * 100
    if dy_pct >= 4.0:
        score += 50
    elif dy_pct >= 3.0:
        score += 40
    elif dy_pct >= 2.0:
        score += 25
    elif dy_pct >= 1.0:
        score += 10

    if pr is not None:
        pr_pct = pr * 100
        if 30 <= pr_pct <= 60:
            score += 30
        elif 20 <= pr_pct < 30 or 60 < pr_pct <= 75:
            score += 15
        elif pr_pct > 100:
            score -= 20

    if dy_pct > 8.0:
        score -= 15

    return _clamp(score)


def score_financial(info: dict) -> float:
    """財務健全性スコア（0〜100）"""
    score = 0.0
    roe = info.get("roe")
    de  = info.get("debt_to_equity")
    cr  = info.get("current_ratio")

    if roe is not None:
        roe_pct = roe * 100
        if roe_pct >= 15:
            score += 35
        elif roe_pct >= 10:
            score += 25
        elif roe_pct >= 5:
            score += 10
        elif roe_pct < 0:
            score -= 20

    if de is not None:
        if de < 50:
            score += 35
        elif de < 100:
            score += 20
        elif de < 200:
            score += 5
        else:
            score -= 10

    if cr is not None:
        if cr >= 2.0:
            score += 30
        elif cr >= 1.5:
            score += 20
        elif cr >= 1.0:
            score += 10
        else:
            score -= 15
    else:
        score += 10  # データ未取得時は中立値（上場企業のCR1.0相当）

    return _clamp(score)


def score_growth(info: dict) -> float:
    """成長性スコア（0〜100）"""
    score = 50.0
    rg = info.get("revenue_growth")
    eg = info.get("earnings_growth")

    if rg is not None:
        rg_pct = rg * 100
        if rg_pct >= 15:
            score += 25
        elif rg_pct >= 5:
            score += 15
        elif rg_pct >= 0:
            score += 5
        else:
            score -= 15

    if eg is not None:
        eg_pct = eg * 100
        if eg_pct >= 15:
            score += 25
        elif eg_pct >= 5:
            score += 15
        elif eg_pct >= 0:
            score += 5
        else:
            score -= 15

    return _clamp(score)


def score_value(info: dict) -> float:
    """割安度スコア（0〜100）"""
    score = 50.0
    per = info.get("per")
    pbr = info.get("pbr")

    if per is not None and per > 0:
        if per <= 10:
            score += 30
        elif per <= 15:
            score += 20
        elif per <= 20:
            score += 10
        elif per <= 30:
            score += 0
        else:
            score -= 15

    if pbr is not None and pbr > 0:
        if pbr <= 1.0:
            score += 20
        elif pbr <= 1.5:
            score += 10
        elif pbr <= 3.0:
            score += 0
        else:
            score -= 10

    return _clamp(score)


def calc_total_score(info: dict, weights: dict = None) -> dict:
    """総合スコアと内訳を計算する。weights を省略すると config.py のデフォルト重みを使用。"""
    d = score_dividend(info)
    f = score_financial(info)
    g = score_growth(info)
    v = score_value(info)

    w = weights if weights else SCORE_WEIGHTS
    total = (
        d * w["dividend"]
        + f * w["financial"]
        + g * w["growth"]
        + v * w["value"]
    )

    dy = info.get("dividend_yield")
    return {
        "total_score":     round(total, 1),
        "dividend_score":  round(d, 1),
        "financial_score": round(f, 1),
        "growth_score":    round(g, 1),
        "value_score":     round(v, 1),
        "dividend_yield":  round(dy * 100, 2) if dy else None,
        "per":             info.get("per"),
        "roe":             round(info["roe"] * 100, 1) if info.get("roe") else None,
    }


def score_label(score: float) -> str:
    if score >= 70:
        return "★★★ 優秀"
    elif score >= 55:
        return "★★ 良好"
    elif score >= 40:
        return "★ 普通"
    else:
        return "要注意"


def get_cached_score(ticker: str):
    """DBキャッシュからスコアを取得する。有効期限切れまたは未存在はNoneを返す"""
    try:
        from db.database import get_session, ScoreCache
        session = get_session()
        row = session.query(ScoreCache).filter_by(ticker=ticker).first()
        session.close()
        if row is None:
            return None
        age = datetime.utcnow() - row.updated_at
        if age > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return {
            "total_score":     row.total_score,
            "dividend_score":  row.dividend_score,
            "financial_score": row.financial_score,
            "growth_score":    row.growth_score,
            "value_score":     row.value_score,
            "dividend_yield":  row.dividend_yield,
            "per":             row.per,
            "roe":             row.roe,
        }
    except Exception:
        return None


def save_score_cache(ticker: str, scores: dict):
    """スコアをDBにキャッシュ保存する"""
    try:
        from db.database import get_session, ScoreCache
        session = get_session()
        row = session.query(ScoreCache).filter_by(ticker=ticker).first()
        if row is None:
            row = ScoreCache(ticker=ticker)
            session.add(row)
        row.total_score     = scores["total_score"]
        row.dividend_score  = scores["dividend_score"]
        row.financial_score = scores["financial_score"]
        row.growth_score    = scores["growth_score"]
        row.value_score     = scores["value_score"]
        row.dividend_yield  = scores.get("dividend_yield")
        row.per             = scores.get("per")
        row.roe             = scores.get("roe")
        row.updated_at      = datetime.utcnow()
        session.commit()
        session.close()
    except Exception:
        pass
