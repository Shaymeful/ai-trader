"""Reconciliation logic to sync local state with broker state."""

import logging

from src.app.config import Config
from src.app.models import Position
from src.app.state import BotState
from src.broker.base import Broker
from src.risk.manager import RiskManager

logger = logging.getLogger(__name__)


class ReconciliationResult:
    """Result of reconciliation with broker."""

    def __init__(self):
        self.broker_open_orders_count = 0
        self.local_orders_added = 0
        self.broker_positions_count = 0
        self.positions_synced = 0
        self.positions_added = 0
        self.positions_removed = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "broker_open_orders": self.broker_open_orders_count,
            "local_orders_added": self.local_orders_added,
            "broker_positions": self.broker_positions_count,
            "positions_synced": self.positions_synced,
            "positions_added": self.positions_added,
            "positions_removed": self.positions_removed,
        }


def reconcile_with_broker(
    config: Config, broker: Broker, state: BotState, risk_manager: RiskManager | None = None
) -> ReconciliationResult:
    """
    Reconcile local state with broker state.

    This function:
    1. Pulls open orders from broker and updates state.submitted_client_order_ids
    2. Pulls positions from broker and updates risk_manager positions if provided

    Args:
        config: Trading configuration
        broker: Broker instance to query
        state: Bot state to update
        risk_manager: Optional risk manager to sync positions

    Returns:
        ReconciliationResult with counts of what was reconciled
    """
    result = ReconciliationResult()

    logger.info("Starting reconciliation with broker...")

    # Step 1: Reconcile open orders
    logger.info("Fetching open orders from broker...")
    try:
        broker_open_orders = broker.get_open_orders()
        result.broker_open_orders_count = len(broker_open_orders)
        logger.info(f"Broker has {result.broker_open_orders_count} open orders")

        # Track what we had before
        local_orders_before = set(state.submitted_client_order_ids)

        # Find orders to add (broker has, we don't)
        orders_to_add = broker_open_orders - local_orders_before
        result.local_orders_added = len(orders_to_add)

        # Add broker's open orders to our state (union, not replace)
        # IMPORTANT: We never remove orders from submitted_client_order_ids
        # This field is a cumulative historical record for idempotency,
        # not just current open orders. Removing filled/canceled orders
        # would break idempotency checks on restart.
        state.submitted_client_order_ids.update(broker_open_orders)

        if orders_to_add:
            logger.info(f"Added {result.local_orders_added} orders to local state from broker:")
            for order_id in orders_to_add:
                logger.info(f"  + {order_id}")

        # Note: We do NOT remove orders from submitted_client_order_ids
        # even if they're not in broker's open orders anymore, because:
        # 1. They might have been filled/canceled (not an error)
        # 2. submitted_client_order_ids is used for idempotency across restarts
        # 3. Removing them would allow duplicate submissions

        if not orders_to_add:
            logger.info("No new orders from broker (state already up-to-date)")

    except Exception as e:
        logger.error(f"Error reconciling orders: {e}")

    # Step 2: Reconcile positions (if risk_manager provided)
    if risk_manager:
        logger.info("Fetching positions from broker...")
        try:
            broker_positions = broker.get_positions()
            result.broker_positions_count = len(broker_positions)
            logger.info(f"Broker has {result.broker_positions_count} positions")

            # Get local positions
            local_positions = {pos.symbol: pos for pos in risk_manager.get_positions()}

            # Sync each broker position
            for symbol, (qty, avg_price) in broker_positions.items():
                if symbol in local_positions:
                    local_pos = local_positions[symbol]
                    # Update if different
                    if local_pos.quantity != qty or local_pos.avg_price != avg_price:
                        logger.info(
                            f"Syncing position {symbol}: broker={qty}@{avg_price}, "
                            f"local={local_pos.quantity}@{local_pos.avg_price}"
                        )
                        risk_manager.positions[symbol] = Position(
                            symbol=symbol,
                            quantity=qty,
                            avg_price=avg_price,
                            current_price=avg_price,  # Use broker avg as initial price
                        )
                        result.positions_synced += 1
                    else:
                        logger.info(f"Position {symbol} matches broker: {qty}@{avg_price}")
                else:
                    # New position from broker
                    logger.info(f"Adding position from broker: {symbol} {qty}@{avg_price}")
                    risk_manager.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=qty,
                        avg_price=avg_price,
                        current_price=avg_price,
                    )
                    result.positions_added += 1

            # Remove positions we have locally but broker doesn't
            broker_symbols = set(broker_positions.keys())
            local_symbols = set(local_positions.keys())
            symbols_to_remove = local_symbols - broker_symbols

            for symbol in symbols_to_remove:
                logger.info(
                    f"Removing position {symbol} (not in broker): "
                    f"{local_positions[symbol].quantity}@{local_positions[symbol].avg_price}"
                )
                del risk_manager.positions[symbol]
                result.positions_removed += 1

            if (
                result.positions_synced == 0
                and result.positions_added == 0
                and result.positions_removed == 0
            ):
                logger.info("Local positions match broker (no changes needed)")

        except Exception as e:
            logger.error(f"Error reconciling positions: {e}")

    logger.info("Reconciliation complete")
    logger.info(f"Summary: {result.to_dict()}")

    return result
