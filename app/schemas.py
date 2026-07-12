from pydantic import BaseModel


class ChannelCreate(BaseModel):
    name: str
    color: str = "#8a8a8a"
    channel_type: str | None = None


class ChannelUpdate(BaseModel):
    name: str
    color: str
    channel_type: str | None = None


class PayoutPeriodCreate(BaseModel):
    label: str
    income_amount: float = 0
    receiving_channel_id: int | None = None


class PayoutPeriodUpdate(BaseModel):
    income_amount: float
    receiving_channel_id: int | None = None


class ExpenseCreate(BaseModel):
    name: str
    amount: float
    payout_period_id: int
    channel_id: int


class TransferCreate(BaseModel):
    payout_period_id: int
    from_channel_id: int
    to_channel_id: int
    amount: float


class TransferUpdate(BaseModel):
    amount: float


class AssetCreate(BaseModel):
    name: str
    amount: float
    channel_id: int | None = None


class AssetUpdate(BaseModel):
    name: str
    amount: float
    channel_id: int | None = None


class GoalCreate(BaseModel):
    name: str
    target: float
    months: int = 1
    channel_id: int | None = None
    round_up_to_hundred: bool = False


class GoalUpdate(BaseModel):
    name: str
    target: float
    months: int
    channel_id: int | None = None
    round_up_to_hundred: bool = False


class GoalContributionCreate(BaseModel):
    goal_id: int
    channel_id: int
    payout_period_id: int
    amount: float


class GoalContributionUpdate(BaseModel):
    amount: float


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
    name: str
    limit: float
    used: float = 0
    channel_id: int | None = None


class CreditLineUpdate(BaseModel):
    name: str
    limit: float
    used: float
    channel_id: int | None = None
