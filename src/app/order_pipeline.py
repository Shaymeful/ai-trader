"""Centralized order submission pipeline with enforced risk checks."""

import logging
from decimal import Decimal

from src.app.config import Config
from src.app.models import FillRecord, OrderRecord, OrderSide, OrderType, Signal, TradeRecord
from src.app.state import BotState, build_client_order_id, save_state
from src.broker.base import Broker
from src.risk import RiskManager

logger = logging.getLogger("ai-trader.order_pipeline")


class OrderSubmissionResult:
    """Result of an order submission attempt."""

    def __init__(self, success: bool, reason: str, order=None, client_order_id: str | None = None):
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
    strategy_name: str = "SMA",
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
        strategy_name=strategy_name,
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
            client_order_id=client_order_id,
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
            client_order_id=client_order_id,
        )

    logger.info("    Idempotency check: PASSED")

    # Step 4: Risk check - signal
    risk_check = risk_manager.check_signal(signal)
    if not risk_check:
        logger.warning(f"    Risk check FAILED: {risk_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Risk check failed: {risk_check.reason}",
            client_order_id=client_order_id,
        )

    logger.info("    Risk check: PASSED")

    # Step 5: Risk check - quantity
    qty_check = risk_manager.check_order_quantity(quantity)
    if not qty_check:
        logger.warning(f"    Quantity check FAILED: {qty_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Quantity check failed: {qty_check.reason}",
            client_order_id=client_order_id,
        )

    logger.info("    Quantity check: PASSED")

    # Step 5a: Risk check - order notional
    if signal.price is None:
        logger.error("    Signal price is None, cannot check notional")
        return OrderSubmissionResult(
            success=False,
            reason="Signal price is required for notional check",
            client_order_id=client_order_id,
        )

    notional_check = risk_manager.check_order_notional(quantity, signal.price)
    if not notional_check:
        logger.warning(f"    Notional check FAILED: {notional_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Notional check failed: {notional_check.reason}",
            client_order_id=client_order_id,
        )

    logger.info("    Notional check: PASSED")

    # Step 5b: Risk check - positions exposure
    exposure_check = risk_manager.check_positions_exposure(quantity, signal.price)
    if not exposure_check:
        logger.warning(f"    Exposure check FAILED: {exposure_check.reason}")
        return OrderSubmissionResult(
            success=False,
            reason=f"Exposure check failed: {exposure_check.reason}",
            client_order_id=client_order_id,
        )

    logger.info("    Exposure check: PASSED")

    # Step 5c: Get quote and check spread (cost controls)
    quote = broker.get_quote(signal.symbol)
    logger.info(
        f"    Quote: bid=${quote.bid}, ask=${quote.ask}, mid=${quote.mid}, "
        f"spread={quote.spread_bps:.2f} bps"
    )

    # Check if spread exceeds maximum
    if quote.spread_bps > config.max_spread_bps:
        logger.warning(
            f"    Spread check FAILED: spread={quote.spread_bps:.2f} bps > "
            f"max={config.max_spread_bps} bps"
        )
        return OrderSubmissionResult(
            success=False,
            reason=f"Spread too wide: {quote.spread_bps:.2f} bps > {config.max_spread_bps} bps",
            client_order_id=client_order_id,
        )

    logger.info("    Spread check: PASSED")

    # Step 5d: Calculate order type and limit price
    order_type = OrderType.LIMIT if config.use_limit_orders else OrderType.MARKET
    limit_price = None
    expected_price = quote.expected_entry_price(signal.side)

    if order_type == OrderType.LIMIT:
        # Calculate limit price: slightly inside spread
        # For BUY: min(ask, mid + spread*0.25)
        # For SELL: max(bid, mid - spread*0.25)
        quarter_spread = quote.spread / Decimal("4")
        if signal.side == OrderSide.BUY:
            limit_price = min(quote.ask, quote.mid + quarter_spread)
        else:  # SELL
            limit_price = max(quote.bid, quote.mid - quarter_spread)

        logger.info(f"    Limit price: ${limit_price} (expected entry: ${expected_price})")

        # Step 5e: Check minimum edge requirement (if configured)
        if config.min_edge_bps > 0:
            # Edge = (limit_price - expected_price) / expected_price * 10000
            # For BUY: negative edge is good (buying below expected)
            # For SELL: positive edge is good (selling above expected)
            edge_abs = limit_price - expected_price
            if expected_price != 0:
                edge_bps = (edge_abs / expected_price) * Decimal("10000")
            else:
                edge_bps = Decimal("0")

            # For BUY, we want edge_bps < 0 (limit below expected)
            # For SELL, we want edge_bps > 0 (limit above expected)
            # Magnitude must be >= min_edge_bps
            if signal.side == OrderSide.BUY:
                if edge_bps > -config.min_edge_bps:
                    logger.warning(
                        f"    Edge check FAILED: edge={edge_bps:.2f} bps, "
                        f"required < -{config.min_edge_bps} bps"
                    )
                    return OrderSubmissionResult(
                        success=False,
                        reason=f"Insufficient edge: {edge_bps:.2f} bps",
                        client_order_id=client_order_id,
                    )
            else:  # SELL
                if edge_bps < config.min_edge_bps:
                    logger.warning(
                        f"    Edge check FAILED: edge={edge_bps:.2f} bps, "
                        f"required > {config.min_edge_bps} bps"
                    )
                    return OrderSubmissionResult(
                        success=False,
                        reason=f"Insufficient edge: {edge_bps:.2f} bps",
                        client_order_id=client_order_id,
                    )

            logger.info(f"    Edge check: PASSED (edge={edge_bps:.2f} bps)")

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
            client_order_id=client_order_id,
        )

    # Step 6: Submit order to broker (ONLY if all checks passed and NOT dry-run)
    try:
        order = broker.submit_order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            client_order_id=client_order_id,
            order_type=order_type,
            limit_price=limit_price,
        )
        logger.info(
            f"    Order submitted: {order.type.value.upper()} {order.side.value.upper()} "
            f"{order.quantity} shares @ ${order.filled_price}"
        )
    except Exception as e:
        logger.error(f"    Error submitting order: {e}")
        return OrderSubmissionResult(
            success=False, reason=f"Broker error: {e}", client_order_id=client_order_id
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
        status=order.status.value,
    )
    write_order_to_csv_fn(order_record, run_id)

    # Step 8: Add to state and save (ONLY after successful submission)
    state.submitted_client_order_ids.add(client_order_id)
    save_state(state)

    # Step 9: Update risk manager if filled
    if order.status.value == "filled":
        # Calculate slippage metrics
        slippage_abs = order.filled_price - expected_price
        if expected_price != 0:
            slippage_bps = (slippage_abs / expected_price) * Decimal("10000")
        else:
            slippage_bps = Decimal("0")

        # Record fill with cost tracking
        fill_record = FillRecord(
            timestamp=order.filled_at,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.filled_price,
            client_order_id=client_order_id,
            broker_order_id=order.id,
            run_id=run_id,
            expected_price=expected_price,
            slippage_abs=slippage_abs,
            slippage_bps=slippage_bps,
            spread_bps_at_submit=quote.spread_bps,
        )
        write_fill_to_csv_fn(fill_record, run_id)

        # Update position
        qty_signed = quantity if signal.side == OrderSide.BUY else -quantity
        risk_manager.update_position(signal.symbol, qty_signed, order.filled_price)

        # Record trade with cost tracking
        trade = TradeRecord(
            timestamp=order.filled_at,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.filled_price,
            order_id=order.id,
            client_order_id=client_order_id,
            run_id=run_id,
            reason=signal.reason,
            expected_price=expected_price,
            slippage_abs=slippage_abs,
            slippage_bps=slippage_bps,
            spread_bps_at_submit=quote.spread_bps,
        )
        write_trade_to_csv_fn(trade, run_id)
        logger.info(f"    Trade recorded: slippage={slippage_bps:.2f} bps")

    return OrderSubmissionResult(
        success=True,
        reason="Order submitted successfully",
        order=order,
        client_order_id=client_order_id,
    )
