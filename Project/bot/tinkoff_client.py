 
import asyncio
from datetime import datetime, timedelta
import logging
import pandas as pd

from tinkoff.invest import (
    AsyncClient, Client, CandleInterval, SubscriptionInterval, CandleInstrument,
    OrderDirection, OrderType, PostOrderRequest, GetOrdersRequest, OrderExecutionReportStatus,
    PositionsRequest, PortfolioRequest
)
from tinkoff.invest.utils import now
from uuid import uuid4

from config import TINKOFF_API_TOKEN, TINKOFF_ACCOUNT_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Поиск Figi (Financial Instrument Global Identifier) по тикеру
async def figiByTicker(ticker):
	with Client(TINKOFF_API_TOKEN) as client:
		instruments = client.instruments.shares()
		for instrument in instruments.instruments:
			if instrument.ticker == ticker:
				logger.info(f"Found FIGI for {ticker}: {instrument.figi} ({instrument.name})")
				return instrument.figi
		logger.warning(f"FIGI not found for ticker: {ticker}")
		return ""

# Запрашиваем пропущенные данные 
async def fetch_historical_candles(figi, interval, start_date, end_date):
    with Client(TINKOFF_API_TOKEN) as client:
        candles = []
        current_start = start_date
        while current_start < end_date:
            temp_end = current_start + timedelta(days=7)  
            if temp_end > end_date:
                temp_end = end_date
            try:
                _candles = client.get_all_candles(
                    figi=figi,
                    from_=current_start,
                    to=temp_end,
                    interval=interval
                )
                candles.extend(_candles)
                current_start = temp_end
            except Exception as e:
                print(f"Error fetching data from {current_start} to {temp_end}: {e}")
                break
        data = {
            'time': [candle.time for candle in candles],
            'open': [candle.open.units + candle.open.nano / 1e9 for candle in candles],
            'high': [candle.high.units + candle.high.nano / 1e9 for candle in candles],
            'low': [candle.low.units + candle.low.nano / 1e9 for candle in candles],
            'close': [candle.close.units + candle.close.nano / 1e9 for candle in candles],
            'volume': [candle.volume for candle in candles]
        }
        pd.DataFrame(data).to_csv('1.csv')
        return data

async def place_order(figi: str, quantity: int, direction: OrderDirection, order_type: OrderType = OrderType.ORDER_TYPE_MARKET):
    order_id = str(uuid4()) # Generate unique ID 
    logger.info(f"Attempting to place order: {direction.name} {quantity} units of {figi}, OrderID: {order_id}")
    try:
        async with AsyncClient(TINKOFF_API_TOKEN) as client:
            request = PostOrderRequest(
                figi=figi,
                quantity=quantity,
                direction=direction,
                account_id=TINKOFF_ACCOUNT_ID,
                order_type=order_type,
                order_id=order_id
            )
            response = await client.orders.post_order(
                figi=figi,
                quantity=quantity,
                direction=direction,
                account_id=TINKOFF_ACCOUNT_ID,
                order_type=order_type,
                order_id=order_id
            )
            logger.info(f"Order placement response: {response.execution_report_status}, Order ID: {response.order_id}, Executed: {response.lots_executed}")

            if response.execution_report_status in [OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_NEW, OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_PARTIALLYFILL, OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL]:
                 logger.info("Order submitted/executed successfully.")
                 return True
            else:
                 logger.error(f"Order placement failed/rejected: Status {response.execution_report_status.name}, Message: {response.message}")
                 return False

    except Exception as e:
        logger.error(f"Error placing order {order_id}: {e}", exc_info=True)
        return False

async def get_current_position_lots(figi: str) -> int:
    logger.debug(f"Getting current position for FIGI: {figi}")
    try:
        async with AsyncClient(TINKOFF_API_TOKEN) as client:

            positions = await client.operations.get_positions(account_id=TINKOFF_ACCOUNT_ID)

            for security in positions.securities:
                if security.figi == figi:
                    position_lots = security.balance 
                    logger.info(f"Current position for {figi}: {position_lots} lots")
                    return int(position_lots) 

            logger.info(f"No current position found for FIGI: {figi}")
            return 0
    except Exception as e:
        logger.error(f"Error getting current position for {figi}: {e}", exc_info=True)
        return 0 


async def has_open_orders(figi: str | None = None) -> bool:
    logger.debug(f"Checking for open orders (FIGI: {figi or 'Any'})")
    try:
        async with AsyncClient(TINKOFF_API_TOKEN) as client:
            orders_response = await client.orders.get_orders(account_id=TINKOFF_ACCOUNT_ID)
            for order in orders_response.orders:

                is_active = order.execution_report_status in [
                    OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_NEW,
                    OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_PARTIALLYFILL
                ]

                matches_figi = (figi is None or order.figi == figi)

                if is_active and matches_figi:
                    logger.info(f"Found active open order: ID {order.order_id}, FIGI {order.figi}, Status {order.execution_report_status.name}")
                    return True
            logger.debug("No active open orders found matching criteria.")
            return False
    except Exception as e:
        logger.error(f"Error checking open orders: {e}", exc_info=True)
        return False