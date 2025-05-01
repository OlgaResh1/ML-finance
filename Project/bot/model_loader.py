 
import pandas as pd
from neuralforecast import NeuralForecast
from config import MODEL_PATH
import logging

logger = logging.getLogger(__name__)

class TradingModel:
	def __init__(self, model_path: str):
		try:
			self.model = NeuralForecast.load(model_path)
			logger.info(f"Model loaded successfully from {model_path}")
		except Exception as e:
			logger.error(f"Failed to load model from {model_path}: {e}")
			self.model = None

	def predict(self, input_df: pd.DataFrame) -> pd.DataFrame | None:
		if not self.model or input_df.empty:
			logger.warning("Model not loaded or input data is empty, cannot predict.")
			return None

		prepared_df = self._prepare_data_for_nf(input_df.copy())
		if prepared_df is None or len(prepared_df) < 32:
			logger.error("Not enough historical data or preparation failed for model prediction")
			return None

		predictions = self.model.predict(prepared_df, S=1) 
		logger.info(f"Model prediction successful.")
		return predictions

	def _prepare_data_for_nf(self, df: pd.DataFrame) -> pd.DataFrame | None:
		if df.empty:
			logger.warning("Input DataFrame for preparation is empty.")
			return None
		df_prepared = df.copy()
		df_prepared['unique_id'] = 'SBER' 
		df_prepared.reset_index(inplace=True) 
		df_prepared.rename(columns={'time': 'ds', 'close': 'y'}, inplace=True) 
		df_prepared['ds'] = pd.to_datetime(df_prepared['ds'], utc=True)
		required_cols = ['unique_id', 'ds', 'y']
		return df_prepared[required_cols]

trading_model = TradingModel(MODEL_PATH)