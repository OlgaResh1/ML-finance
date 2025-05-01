 
import asyncio
import logging
import pandas as pd
from datetime import timedelta
from tinkoff.invest import (
    AsyncClient,
    Client,
	Candle,
    CandleInstrument,
    SubscriptionInterval,
    HistoricCandle,
    CandleInterval,
	OrderDirection
)
from tinkoff.invest.utils import now, quotation_to_decimal
import sys

from config import (TINKOFF_API_TOKEN, TICKER, ORDER_QUANTITY, HISTORY_DEPTH_FOR_INDICATORS)

from database import save_to_db, get_recent_data, create_db_and_tables

from tinkoff_client import (figiByTicker, fetch_historical_candles,
                           place_order, get_current_position_lots, has_open_orders)
from tinkoff.invest.async_services import AsyncMarketDataStreamManager

from indicators import calculate_indicators
from model_loader import trading_model 
from strategy import generate_signal, BUY, SELL, HOLD


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

recent_candles_df = pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
figi = None 
SUBSCRIPTION_INTERVAL = SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_HOUR
CANDLE_INTERVAL = CandleInterval.CANDLE_INTERVAL_HOUR


def candle_to_dict(candle: Candle | HistoricCandle) -> dict | None:
	try:
		return {
			'time': candle.time,
			'open': float(quotation_to_decimal(candle.open)),
			'high': float(quotation_to_decimal(candle.high)),
			'low': float(quotation_to_decimal(candle.low)),
			'close': float(quotation_to_decimal(candle.close)),
			'volume': candle.volume
		}
	except Exception as e:
		logger.error(f"Error converting candle to dict: {e} - Candle: {candle}")
		return None


async def process_new_candle(candle_data: dict):
	global recent_candles_df, figi

	new_row = pd.DataFrame([candle_data]).set_index('time')
	recent_candles_df = pd.concat([recent_candles_df, new_row])

	logger.info(f"Processing new candle: {new_row.iloc[0].to_dict()}")
	save_to_db(new_row.reset_index()) 

	if len(recent_candles_df) < HISTORY_DEPTH_FOR_INDICATORS:
		logger.info(f"Not enough historical data ({len(recent_candles_df)}/{HISTORY_DEPTH_FOR_INDICATORS}) for strategy calculation.")
		return

	indicator_values = calculate_indicators(recent_candles_df.copy())
	if indicator_values.empty:
		logger.warning("Indicator calculation failed.")
		return
	logger.debug(f"Latest Indicators: {indicator_values.iloc[-1].to_dict()}")

	predictions = trading_model.predict(recent_candles_df.copy()) 

	if predictions is None or predictions.empty:
		logger.warning("Model prediction failed or returned empty. Skipping trade logic.")
		return

	latest_candle_time = recent_candles_df.index[-1]
	try:
			next_pred_time = latest_candle_time + timedelta(hours=1) 
			relevant_prediction = predictions[predictions['ds'] >= next_pred_time].sort_values('ds').iloc[[0]]

			pred_close = relevant_prediction['AutoTSMixerx-median'].iloc[0] 
			current_close = recent_candles_df['close'].iloc[-1]
			predicted_direction = 1 if pred_close > current_close else 0

			prediction_input = pd.DataFrame([{'Pred_Direction': predicted_direction}], index=[latest_candle_time])

			logger.debug(f"Latest Prediction (for {next_pred_time}): Median={pred_close:.2f}, Current Close={current_close:.2f}, Direction={predicted_direction}")

	except (IndexError, KeyError) as e:
			logger.error(f"Could not extract relevant prediction: {e}. Predictions DF:\n{predictions}")
			return  

	signal = generate_signal(indicator_values, prediction_input)

	current_lots = await get_current_position_lots(figi)
	has_active_order = await has_open_orders(figi)

	if has_active_order:
		logger.info("Skipping trade decision: Active order found for this instrument.")
		return

	if signal == BUY and current_lots == 0:
		logger.info(f"BUY Signal received. Current position: {current_lots}. Placing BUY order for {ORDER_QUANTITY} lot(s).")
		await place_order(figi, ORDER_QUANTITY, OrderDirection.ORDER_DIRECTION_BUY)
	elif signal == HOLD and current_lots > 0:
		logger.info(f"EXIT (from HOLD signal). Current position: {current_lots}. Placing SELL order.")
		await place_order(figi, current_lots, OrderDirection.ORDER_DIRECTION_SELL)
	elif signal == SELL and current_lots > 0:
			logger.info(f"SELL Signal received. Current position: {current_lots}. Placing SELL order.")
			await place_order(figi, current_lots, OrderDirection.ORDER_DIRECTION_SELL)
	else:
		logger.info(f"Signal: {signal} ({'BUY' if signal==BUY else 'SELL' if signal==SELL else 'HOLD'}). Current position: {current_lots}. No action taken.")


async def stream_data_handler(candle):
	try:
		candle_dict = candle_to_dict(candle)
		if candle_dict:
			await process_new_candle(candle_dict)

	except asyncio.CancelledError:
		logger.info("Market data stream cancelled.")
	except Exception as e:
		logger.error(f"Error in market data stream: {e}", exc_info=True)



async def backfill_missing_data(figi_to_load: str):
	global recent_candles_df
	logger.info("Starting load data ...")

	db_data = get_recent_data(HISTORY_DEPTH_FOR_INDICATORS + 100) 

	if not db_data.empty:
			db_data.columns = ['open', 'high', 'low', 'close', 'volume'] 
			recent_candles_df = db_data
			last_record_time = recent_candles_df.index[-1]
			last_record_time = last_record_time.tz_localize('UTC')
			logger.info(f"Loaded {len(recent_candles_df)} records from DB. Last record: {last_record_time}")
			start_fetch_date = last_record_time + timedelta(seconds=1) 
	else:
			logger.info("No existing data found in DB. Fetching initial historical data.")
			start_fetch_date = now() - timedelta(days=10)

	end_fetch_date = now()
	if start_fetch_date >= end_fetch_date:
		logger.info("Database is up-to-date. No backfill needed.")
		return 
	
	logger.info(f"Fetching missing historical data from {start_fetch_date} to {end_fetch_date}")
	missing_candles = await fetch_historical_candles(figi_to_load, CANDLE_INTERVAL, start_fetch_date, end_fetch_date)

	recent_candles_df = pd.concat([recent_candles_df if not recent_candles_df.empty else None, pd.DataFrame(missing_candles) ], ignore_index=True)
	save_to_db(pd.DataFrame(missing_candles)) 


async def main():
	global figi, recent_candles_df
	logger.info(f"Starting bot for ticker: {TICKER}")

	figi = await figiByTicker(TICKER)
	if not figi:
		logger.error("Could not retrieve FIGI. Exiting.")
		return
	logger.info(f"Using FIGI: {figi}")

	create_db_and_tables()

	await backfill_missing_data(figi)

	async with AsyncClient(TINKOFF_API_TOKEN) as client:
		market_data_stream: AsyncMarketDataStreamManager = (
            client.create_market_data_stream()
        )
		#market_data_stream = client.create_market_data_stream()
		logger.info(f"Subscribing to candles: FIGI={figi}, Interval={SUBSCRIPTION_INTERVAL.name}")
		market_data_stream.candles.waiting_close().subscribe(  # Подписка на новые данные, приходят только в часы работы биржи)
			[
				CandleInstrument(
					figi=figi,
					interval=SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_HOUR, 

							# SUBSCRIPTION_INTERVAL_ONE_MINUTE 
							# SUBSCRIPTION_INTERVAL_ONE_HOUR
							# SUBSCRIPTION_INTERVAL_FIVE_MINUTES
				)
			]
		)
		async for marketdata in market_data_stream:
			if marketdata.candle:
				await stream_data_handler(marketdata.candle)

			elif marketdata.trade:
				logger.debug(f"Received trade: {marketdata.trade}")
			elif marketdata.orderbook:
				logger.debug(f"Received orderbook update: {marketdata.orderbook}")
			elif marketdata.trading_status:
				logger.info(f"Trading status update: {marketdata.trading_status}")
			elif marketdata.last_price:
					logger.debug(f"Last price update: {marketdata.last_price}")



if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		logger.info("Bot stopped manually.")
	except Exception as e:
		logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)