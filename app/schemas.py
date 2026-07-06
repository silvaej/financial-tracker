from pydantic import BaseModel


class ChannelCreate(BaseModel):
    name: str
    color: str = "#8a8a8a"
    funding_source_channel_id: int | None = None


class ChannelUpdate(BaseModel):
    name: str
    color: str
    funding_source_channel_id: int | None = None


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


class AssetUpdate(BaseModel):
    name: str
    amount: float


class GoalCreate(BaseModel):
    name: str
    target: float
    allocated: float = 0
    months: int = 1
    channel_id: int | None = None
    round_up_to_hundred: bool = False


class GoalUpdate(BaseModel):
    name: str
    target: float
    allocated: float
    months: int
    channel_id: int | None = None
    round_up_to_hundred: bool = False


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
