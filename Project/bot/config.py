 
import os
from dotenv import load_dotenv

load_dotenv()

TINKOFF_API_TOKEN = os.environ.get("TINKOFF_API_TOKEN")
TINKOFF_ACCOUNT_ID = os.environ.get("TINKOFF_ACCOUNT_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")
TICKER = os.environ.get("TICKER", "SBER")
TABLE_NAME = os.environ.get("TABLE_NAME", "sber_day")
TRADE_INTERVAL_HOURS = int(os.environ.get("TRADE_INTERVAL_HOURS", 1))
MODEL_PATH = os.environ.get("MODEL_PATH", "./checkpoints/TSMixerx_1day/")
ORDER_QUANTITY = 1 #int(os.environ.get("ORDER_QUANTITY", 1))


INDICATOR_WINDOW_CCI = 20 
INDICATOR_WINDOW_RSI = 14
INDICATOR_WINDOW_SMA_SHORT = 20
INDICATOR_WINDOW_SMA_LONG = 50
HISTORY_DEPTH_FOR_INDICATORS = 100 # How many candles needed to calculate all indicators/features