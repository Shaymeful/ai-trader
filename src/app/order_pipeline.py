"""Centralized order submission pipeline with enforced risk checks."""
import logging
from typing import Optional

from src.app.config import Config
from src.app.models import Signal, OrderSide, OrderRecord, FillRecord, TradeRecord
from src.app.state import BotState, save_state, build_client_order_id
from src.broker.base import Broker
from src.risk import RiskManager

logger = logging.getLogger("ai-trader.order_pipeline")


class OrderSubmissionResult:
    """Result of an order submission attempt."""

    def __init__(
        self,
        success: bool,
        reason: str,
        order=None,
        client_order_id: Optional[str] = None
    ):
        self.success = success
        self.reason = reason
        self.order = order
        self.client_order_id = client_order_id


def submit_signal_order(
    signal: Signal,
    quantity: int,
    config: Config,
    broker: Broker,
    risk_manager: RiskManager,
    state: BotState,
    run_id: str,
    write_order_to_csv_fn,
    write_fill_to_csv_fn,
    write_trade_to_csv_fn,
    strategy_name: str = "SMA"
) -> OrderSubmissionResult:
    """
    Centralized order submission pipeline with enforced risk checks.

    This is the ONLY function that should submit orders to the broker.
    It guarantees that:
    1. Deterministic client_order_id is computed
    2. Idempotency checks prevent duplicates
    3. ALL RiskManager checks are enforced before broker calls
    4. State is only updated after successful submission
    5. CSV files are only written after successful submission

    In DRY_RUN mode:
    - All checks are performed (idempotency, risk, quantity)
    - Broker is NOT called
    - CSV files are NOT written
    - State is NOT modified
    - Logs what WOULD have happened

    Args:
        signal: Trading signal to execute
        quantity: Order quantity
        config: Bot configuration
        broker: Broker instance
        risk_manager: RiskManager instance
        state: Current bot state
        run_id: Current run ID
        write_order_to_csv_fn: Function to write order records
        write_fill_to_csv_fn: Function to write fill records
        write_trade_to_csv_fn: Function to write trade records
        strategy_name: Strategy identifier for client_order_id

    Returns:
        OrderSubmissionResult with success status, reason, and order (if successful)
    """
    # Step 1: Build deterministic client_order_id
    client_order_id = build_client_order_id(
        symbol=signal.symbol,
        side=signal.side.value,
        signal_timestamp=signal.timestamp,
        strategy_name=strategy_name
    )

    logger.info(f"    Client Order ID: {client_order_id}")

    # Step 2: Idempotency check - state
    if client_order_id in state.submitted_client_order_ids:
        logger.warning(
            f"    Skipping duplicate order (idempotency key already submitted): {client_order_id}"
        )
        return OrderSubmissionResult(
            success=False,
            reason="Duplicate order (already in state)",
            client_order_id=client_order_id
        )

    # Step 3: Idempotency check - broker
    if broker.order_exists(client_order_id):
        logger.warning(
            f"    Skipping duplicate order (idempotency key exists in broker): {client_order_id}"
        )
        # Add to state to prevent future checks
        state.submitted_client_order_ids.add(client_order_id)
        save_state(state)
        return OrderSubmissionResult(
            success=False,
            reason="Duplicate order (already in broker)",
            client_order_id=client_order_id
        )

    logger.info(f"    Idempotency check: PASSED")

    # Step 4: Risk check - signal
    risk_check = risk_manager.check_signal(signal)
    if not risk_check:
        logger.warning(f"    Risk check FAILED: {risk_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Risk check failed: {risk_check.reason}",
            client_order_id=client_order_id
        )

    logger.info(f"    Risk check: PASSED")

    # Step 5: Risk check - quantity
    qty_check = risk_manager.check_order_quantity(quantity)
    if not qty_check:
        logger.warning(f"    Quantity check FAILED: {qty_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Quantity check failed: {qty_check.reason}",
            client_order_id=client_order_id
        )

    logger.info(f"    Quantity check: PASSED")

    # DRY-RUN MODE: Stop before broker call
    if config.dry_run:
        logger.warning(
            f"    DRY_RUN: would submit {signal.side.value.upper()} {quantity} {signal.symbol} "
            f"with client_order_id={client_order_id} (reason={signal.reason})"
        )
        return OrderSubmissionResult(
            success=True,  # Successful dry-run
            reason="Dry-run: order would have been submitted",
            order=None,
            client_order_id=client_order_id
        )

    # Step 6: Submit order to broker (ONLY if all checks passed and NOT dry-run)
    try:
        order = broker.submit_order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            client_order_id=client_order_id
        )
        logger.info(
            f"    Order submitted: {order.side.value.upper()} {order.quantity} "
            f"shares @ ${order.filled_price}"
        )
    except Exception as e:
        logger.error(f"    Error submitting order: {e}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Broker error: {e}",
            client_order_id=client_order_id
        )

    # Step 7: Record order to CSV (ONLY after successful submission)
    order_record = OrderRecord(
        timestamp=order.submitted_at,
        symbol=order.symbol,
        side=order.side.value,
        quantity=order.quantity,
        order_type=order.type.value,
        limit_price=order.price,
        client_order_id=client_order_id,
        broker_order_id=order.id,
        run_id=run_id,
        status=order.status.value
    )
    write_order_to_csv_fn(order_record)

    # Step 8: Add to state and save (ONLY after successful submission)
    state.submitted_client_order_ids.add(client_order_id)
    save_state(state)

    # Step 9: Update risk manager if filled
    if order.status.value == "filled":
        # Record fill
        fill_record = FillRecord(
            timestamp=order.filled_at,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.filled_price,
            client_order_id=client_order_id,
            broker_order_id=order.id,
            run_id=run_id
        )
        write_fill_to_csv_fn(fill_record)

        # Update position
        qty_signed = quantity if signal.side == OrderSide.BUY else -quantity
        risk_manager.update_position(
            signal.symbol,
            qty_signed,
            order.filled_price
        )

        # Record trade (legacy format)
        trade = TradeRecord(
            timestamp=order.filled_at,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.filled_price,
            order_id=order.id,
            client_order_id=client_order_id,
            run_id=run_id,
            reason=signal.reason
        )
        write_trade_to_csv_fn(trade)
        logger.info(f"    Trade recorded to out/trades.csv")

    return OrderSubmissionResult(
        success=True,
        reason="Order submitted successfully",
        order=order,
        client_order_id=client_order_id
    )
