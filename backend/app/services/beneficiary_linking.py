from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.models.beneficiary import Beneficiary
from app.models.user import User
from app.services.recipient_wallet import get_or_create_wallet_row


def _provision_wallet_if_needed(db: DBSession, user_id: str) -> None:
    """FR-12b: create the internal ledger row for this user's custodial
    wallet. Idempotent - a user may be the match for several senders'
    beneficiary records but should only ever get one wallet.

    The real XRPL account isn't generated here (see
    app.services.recipient_wallet.ensure_xrpl_account) - this stays a fast,
    network-free DB write so beneficiary linking never blocks on the
    XRPL Testnet faucet.
    """
    get_or_create_wallet_row(db, user_id)


def _find_matching_user(db: DBSession, mobile_number: str | None, email_address: str | None) -> User | None:
    conditions = []
    if mobile_number:
        conditions.append(User.mobile_number == mobile_number)
    if email_address:
        conditions.append(func.lower(User.email) == email_address.lower())
    if not conditions:
        return None
    return db.query(User).filter(or_(*conditions)).first()


def try_link_beneficiary(db: DBSession, beneficiary: Beneficiary) -> None:
    """FR-12a: attempt to link a freshly-added beneficiary to an existing
    registered account by matching mobile number or email.

    FR-12b: provision that user's wallet the moment linking succeeds.
    FR-12c: if nothing matches, leave the beneficiary unlinked - it will be
    picked up later by link_pending_beneficiaries_for_new_user() if a
    matching account registers afterwards.

    Does not commit its own beneficiary change; the caller is expected to
    do so as part of its own transaction. _provision_wallet_if_needed runs
    first since it commits internally (get_or_create_wallet_row) - doing
    that before mutating the beneficiary means the caller's own commit
    cleanly captures just the linked_user_id change, not a half-finished
    intermediate state.
    """
    if beneficiary.linked_user_id is not None:
        return

    match = _find_matching_user(db, beneficiary.mobile_number, beneficiary.email_address)
    if match is None:
        return

    _provision_wallet_if_needed(db, match.id)
    beneficiary.linked_user_id = match.id
    db.add(beneficiary)


def link_pending_beneficiaries_for_new_user(db: DBSession, user: User) -> None:
    """FR-12c: when a new account registers, retroactively link any
    beneficiary records that were left waiting for exactly this
    mobile/email to appear, and provision the wallet.

    Commits internally since it runs as a follow-up step after the
    registration transaction has already completed.
    """
    pending = (
        db.query(Beneficiary)
        .filter(Beneficiary.linked_user_id.is_(None))
        .filter(
            or_(
                Beneficiary.mobile_number == user.mobile_number,
                func.lower(Beneficiary.email_address) == user.email.lower(),
            )
        )
        .all()
    )
    if not pending:
        return

    _provision_wallet_if_needed(db, user.id)

    for beneficiary in pending:
        beneficiary.linked_user_id = user.id
        db.add(beneficiary)

    db.commit()
