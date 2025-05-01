import logging
from datetime import datetime
import pandas as pd

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Column, DateTime # Import Column and DateTime for timezone
from sqlmodel import Field, SQLModel, Session, create_engine, select, text

from config import DATABASE_URL, TABLE_NAME 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определение модели данных
class Candle(SQLModel, table=True):
    __tablename__ = TABLE_NAME
    time: datetime = Field(primary_key=True)
    open: float
    high: float
    low: float
    close: float
    volume: int
    
engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    try:
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}", exc_info=True)
        raise 

def save_to_db(df: pd.DataFrame):
	if df.empty:
		logger.debug("DataFrame is empty, nothing to save.")
		return
	try:
		duplicates = df[df.duplicated(subset=['time'], keep=False)]
		if not duplicates.empty:
			logger.warning(f"Found {len(duplicates)} duplicate timestamps. Dropping duplicates, keeping first.")
			df = df.drop_duplicates(subset=['time'], keep='first')

		with Session(engine) as session:
			for index, row in df.iterrows():
				stock_data = Candle(
					time=row['time'],
					open=row['open'],
					high=row['high'],
					low=row['low'],
					close=row['close'],
					volume=row['volume']
				)
				session.add(stock_data)
				#logger.info(f"save_data: { row['time'] }")
			session.commit()
	except Exception as e:
		logger.error(f"Error save_data: {e}")

def get_recent_data(limit: int) -> pd.DataFrame:
    logger.debug(f"Fetching last {limit} records from {Candle.__tablename__}")
    candles = []
    try:
        with Session(engine) as session:
            statement = select(Candle).order_by(Candle.time.desc()).limit(limit)
            results = session.exec(statement).all()
            candles = [candle.model_dump() for candle in results] 
            logger.info(f"Fetched {len(candles)} rows from {Candle.__tablename__}")

    except Exception as e:
        logger.error(f"Error fetching recent data from DB: {e}", exc_info=True)
        return pd.DataFrame() 

    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)

    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.sort_index(inplace=True)

    float_cols = ['open', 'high', 'low', 'close']
    df[float_cols] = df[float_cols].astype(float)
    df['volume'] = df['volume'].astype(int)

    return df