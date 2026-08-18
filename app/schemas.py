from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# A name/label field that must be non-empty once surrounding whitespace is
# stripped -- StringConstraints(strip_whitespace=True) strips *before* the
# min_length check runs, so a whitespace-only value (e.g. "   ") is rejected
# rather than passing as a "non-empty" 3-character string. See issue #69.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChannelCreate(BaseModel):
    name: NonEmptyStr
    color: str = "#8a8a8a"
    channel_type: str | None = None
    badge_label: str | None = None


class ChannelUpdate(BaseModel):
    name: NonEmptyStr
    color: str
    channel_type: str | None = None


class PayoutPeriodCreate(BaseModel):
    label: NonEmptyStr
    # 0 is legitimate here -- a brand-new payout period with no income
    # configured yet.
    income_amount: float = Field(default=0, ge=0)
    receiving_channel_id: int | None = None
    payout_day: int | None = Field(default=None, ge=1, le=31)


class PayoutPeriodUpdate(BaseModel):
    income_amount: float = Field(ge=0)
    receiving_channel_id: int | None = None
    payout_day: int | None = Field(default=None, ge=1, le=31)


class ExpenseCreate(BaseModel):
    name: NonEmptyStr
    amount: float = Field(gt=0)
    payout_period_id: int
    channel_id: int
    due_day: int | None = Field(default=None, ge=1, le=31)


class TransferCreate(BaseModel):
    payout_period_id: int
    from_channel_id: int
    to_channel_id: int
    amount: float = Field(gt=0)


class TransferUpdate(BaseModel):
    amount: float = Field(gt=0)


class AssetCreate(BaseModel):
    name: NonEmptyStr
    amount: float = Field(gt=0)
    channel_id: int | None = None


class AssetUpdate(BaseModel):
    name: NonEmptyStr
    amount: float = Field(gt=0)
    channel_id: int | None = None


class GoalCreate(BaseModel):
    name: NonEmptyStr
    target: float = Field(gt=0)
    months: int = Field(default=1, gt=0)
    channel_id: int | None = None
    round_up_to_hundred: bool = False


class GoalUpdate(BaseModel):
    name: NonEmptyStr
    target: float = Field(gt=0)
    months: int = Field(gt=0)
    channel_id: int | None = None
    round_up_to_hundred: bool = False


class GoalContributionCreate(BaseModel):
    goal_id: int
    channel_id: int
    payout_period_id: int
    amount: float = Field(gt=0)


class GoalContributionUpdate(BaseModel):
    amount: float = Field(gt=0)


class PlacementUpdate(BaseModel):
    payout_period_id: int
    x: float
    y: float


class CanvasChannelPlacementIn(BaseModel):
    channel_id: int
    x: float
    y: float


class CanvasGoalPlacementIn(BaseModel):
    goal_id: int
    x: float
    y: float


class CanvasTransferIn(BaseModel):
    from_channel_id: int
    to_channel_id: int
    amount: float


class CanvasGoalContributionIn(BaseModel):
    channel_id: int
    goal_id: int
    amount: float


class CanvasSaveIn(BaseModel):
    channel_placements: list[CanvasChannelPlacementIn] = []
    goal_placements: list[CanvasGoalPlacementIn] = []
    transfers: list[CanvasTransferIn] = []
    goal_contributions: list[CanvasGoalContributionIn] = []


class CanvasPreviewOut(BaseModel):
    channel_balances: dict[int, float]
    goal_contributed: dict[int, float]
    unfunded_channel_ids: list[int]
    underfunded_goal_ids: list[int]


class CreditLineCreate(BaseModel):
    name: NonEmptyStr
    limit: float = Field(gt=0)
    # 0 is legitimate here -- a brand-new credit line with nothing charged
    # to it yet.
    used: float = Field(default=0, ge=0)
    channel_id: int | None = None


class CreditLineUpdate(BaseModel):
    name: NonEmptyStr
    limit: float = Field(gt=0)
    used: float = Field(ge=0)
    channel_id: int | None = None


class SignupKeyCreate(BaseModel):
    max_uses: int = Field(default=1, ge=1)
    expires_days: int | None = Field(default=None, ge=1)
