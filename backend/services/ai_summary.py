import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models.ai_summary import AiSummary
from models.signal_output import SignalOutput
from models.price_cache import PriceCache
from models.ticker import Ticker

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are a concise trading signal analyst. Given a ticker's current signal data, produce a brief market summary.

Return ONLY valid JSON with exactly this shape — no markdown fences, no commentary:
{"headline": "One sentence summary", "bullets": ["point 1", "point 2", ...]}

Rules:
- headline: one clear sentence describing the current signal state and what it means for positioning
- bullets: 2-4 short bullet points covering the most important observations
- Use plain English — no internal metric names (no "OBV", "Hurst", "structural_score", "quad_score")
- Speak in terms of: trend alignment, volume confirmation, volatility environment, macro alignment
- Be direct about the signal: if it says buy, say buy; if caution, say caution
- Never give financial advice — describe what the signals show, not what the user should do
- Keep total output under 200 words"""


def _build_prompt(ticker: str, sig: SignalOutput, pc: PriceCache, tk: Ticker) -> str:
    vp = sig.viewpoint or "Neutral"
    conv = sig.conviction
    parts = [
        f"Ticker: {ticker} — {tk.description or ''}",
        f"Asset class: {tk.asset_class or 'Unknown'}, Sector: {tk.sector or 'Unknown'}",
        f"Close: ${pc.close:.2f}" if pc.close else "",
        f"Viewpoint: {vp}",
        f"Conviction: {conv}%" if conv is not None else "Conviction: not calculated",
        f"Trade direction: {sig.trade_direction or 'Neutral'}",
        f"Structural state: {sig.structural_state or 'Unknown'}",
    ]

    if sig.structural_score is not None:
        parts.append(f"Price structure score: {sig.structural_score}/50")
    if sig.volume_score is not None:
        vol_dir = sig.obv_direction or "Neutral"
        confirming = "yes" if sig.obv_confirming else "no"
        parts.append(f"Volume direction: {vol_dir}, confirming trade: {confirming}, score: {sig.volume_score}/15")
    if sig.vix_score is not None:
        parts.append(f"Volatility regime: {sig.vix_regime or 'Unknown'}, score: {sig.vix_score}/15")
    if sig.quad_score is not None:
        align = sig.quad_alignment or "Neutral"
        parts.append(f"Macro quad alignment: {align}, score: {sig.quad_score}")

    if sig.lrr is not None and sig.hrr is not None:
        parts.append(f"Trade LRR: ${sig.lrr:.2f}, HRR: ${sig.hrr:.2f}")

    if sig.warning:
        parts.append("WARNING: price is near the invalidation level")
    if sig.alert:
        parts.append("HIGH CONVICTION ALERT is active")

    if pc.iv30 is not None:
        parts.append(f"IV30: {pc.iv30*100:.1f}%")
    if pc.hv30 is not None:
        parts.append(f"HV30: {pc.hv30*100:.1f}%")
    if pc.rel_iv is not None and tk.ticker not in ("VVIX",):
        parts.append(f"IV Rank: {pc.rel_iv}")

    return "\n".join(p for p in parts if p)


def generate_summary(ticker: str, db: Session, force: bool = False) -> dict | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    if not force:
        existing = db.query(AiSummary).filter(
            AiSummary.ticker == ticker,
            AiSummary.summary_date == today_et,
        ).first()
        if existing:
            return {"headline": existing.headline, "bullets": json.loads(existing.bullets_json or "[]")}

    sig = db.query(SignalOutput).filter(
        SignalOutput.ticker == ticker, SignalOutput.timeframe == "trade"
    ).first()
    if not sig:
        return None

    pc = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if not pc:
        return None

    tk = db.query(Ticker).filter(Ticker.ticker == ticker).first()
    if not tk:
        return None

    prompt = _build_prompt(ticker, sig, pc, tk)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        parsed = json.loads(text)
        headline = parsed.get("headline", "")
        bullets = parsed.get("bullets", [])
    except json.JSONDecodeError:
        logger.warning(f"AI summary for {ticker}: invalid JSON response")
        return None
    except Exception as e:
        logger.warning(f"AI summary for {ticker} failed: {e}")
        return None

    row = db.query(AiSummary).filter(
        AiSummary.ticker == ticker,
        AiSummary.summary_date == today_et,
    ).first()

    if row:
        row.headline = headline
        row.bullets_json = json.dumps(bullets)
        row.model = MODEL
        row.created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    else:
        row = AiSummary(
            ticker=ticker,
            summary_date=today_et,
            headline=headline,
            bullets_json=json.dumps(bullets),
            model=MODEL,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.add(row)

    db.commit()
    return {"headline": headline, "bullets": bullets}


def generate_all_summaries(db: Session):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("AI summaries skipped — ANTHROPIC_API_KEY not set")
        return {"generated": 0, "skipped": 0, "errors": 0}

    tickers = db.query(Ticker).filter(Ticker.active == True).all()
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    existing = {r.ticker for r in db.query(AiSummary.ticker).filter(
        AiSummary.summary_date == today_et
    ).all()}

    generated = 0
    skipped = 0
    errors = 0

    for tk in tickers:
        if tk.ticker in existing:
            skipped += 1
            continue
        try:
            result = generate_summary(tk.ticker, db, force=False)
            if result:
                generated += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning(f"AI summary error for {tk.ticker}: {e}")
            errors += 1

    logger.info(f"AI summaries: {generated} generated, {skipped} skipped, {errors} errors")
    return {"generated": generated, "skipped": skipped, "errors": errors}
