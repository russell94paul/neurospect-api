import enum


class SessionType(str, enum.Enum):
    asia = "asia"
    london = "london"
    ny_am = "ny_am"
    ny_pm = "ny_pm"


class KillZoneType(str, enum.Enum):
    asia = "asia"
    london_open = "london_open"
    ny_am_open = "ny_am_open"
    ny_pm_open = "ny_pm_open"
    london_close = "london_close"


class BiasType(str, enum.Enum):
    bullish = "bullish"
    bearish = "bearish"
    neutral = "neutral"


class OppType(str, enum.Enum):
    below_all = "below_all"
    below_some = "below_some"
    above_all = "above_all"
    above_some = "above_some"


class SetupType(str, enum.Enum):
    consolidation = "consolidation"
    expansion_retracement = "expansion_retracement"
    reversal = "reversal"
    model_2022_ote = "model_2022_ote"
    london = "london"
    daily_bias = "daily_bias"
    smt = "smt"


class PdaType(str, enum.Enum):
    fvg = "fvg"
    order_block = "order_block"
    rejection_block = "rejection_block"
    ote_block = "ote_block"
    breaker = "breaker"


class DisplacementType(str, enum.Enum):
    clean = "clean"
    choppy = "choppy"
    none = "none"


class OutcomeType(str, enum.Enum):
    win = "win"
    loss = "loss"
    breakeven = "breakeven"


class GradeType(str, enum.Enum):
    a_plus = "a_plus"
    a = "a"
    b = "b"
    c = "c"


class ScreenshotPhase(str, enum.Enum):
    before_entry = "before_entry"
    entry = "entry"
    higher_tf = "higher_tf"
    exit = "exit"
    post_trade_review = "post_trade_review"


class TradeStatus(str, enum.Enum):
    pre_trade = "pre_trade"
    active = "active"
    closed = "closed"


class CoachingEventStatus(str, enum.Enum):
    pending = "pending"
    complete = "complete"
    error = "error"
