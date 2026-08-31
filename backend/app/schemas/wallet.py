from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class IncomingTransferOut(BaseModel):
    remittance_id: str
    rlusd_amount: Decimal
    status: str
    xrpl_tx_hash: str | None
    settled_at: datetime | None
    created_at: datetime


class CashOutSummaryOut(BaseModel):
    id: str
    rlusd_amount: Decimal
    fiat_currency: str
    fiat_payout_amount: Decimal
    status: str
    created_at: datetime
    completed_at: datetime | None


class WalletOut(BaseModel):
    """FR-27/FR-28: the recipient's custodial wallet."""

    balance_rlusd: Decimal
    xrpl_address: str | None
    incoming_transfers: list[IncomingTransferOut]
    cash_out_transactions: list[CashOutSummaryOut]
