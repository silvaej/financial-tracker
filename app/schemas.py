from pydantic import BaseModel


class ChannelCreate(BaseModel):
    name: str
    color: str = "#8a8a8a"


class ChannelUpdate(BaseModel):
    name: str
    color: str


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
