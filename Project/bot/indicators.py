 
import pandas as pd
from ta.momentum import StochasticOscillator
from ta.trend import ADXIndicator
from ta.volume import ChaikinMoneyFlowIndicator
import logging

logger = logging.getLogger(__name__)

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
	if df.empty or len(df) < 50:
		logger.warning(f"DataFrame too small for indicator calculation ({len(df)} rows)")
		return pd.DataFrame() 

	df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'}, inplace=True, errors='ignore')

	for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
		if col in df.columns:
			df[col] = pd.to_numeric(df[col], errors='coerce')
		else:
			logger.error(f"Required column {col} missing for indicator calculation.")
			return pd.DataFrame()

	df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])

	indicators = pd.DataFrame(index=df.index)

	# CMF_20
	cmf = ChaikinMoneyFlowIndicator(df['High'], df['Low'], df['Close'], df['Volume'], window=20)
	indicators['CMF_20'] = cmf.chaikin_money_flow()
	indicators['CMF_20_Positive'] = (indicators['CMF_20'] > 0).astype(int)

	# DI_Cross_14
	adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
	indicators['DI+14'] = adx.adx_pos()
	indicators['DI-14'] = adx.adx_neg()
	indicators['DI_Cross_14'] = (indicators['DI+14'] > indicators['DI-14']).astype(int)

	# Stochastic_Cross_5_5
	stoch = StochasticOscillator(df['High'], df['Low'], df['Close'], window=5, smooth_window=5)
	indicators['Stoch_%K_5_5'] = stoch.stoch()
	indicators['Stoch_%D_5_5'] = stoch.stoch_signal()
	indicators['Stochastic_Cross_5_5'] = (indicators['Stoch_%K_5_5'] > indicators['Stoch_%D_5_5']).astype(int)

	indicators['Close'] = df['Close'] 
	indicators = indicators[['Close', 'CMF_20_Positive', 'DI_Cross_14', 'Stochastic_Cross_5_5']]
	logger.info("Indicators calculated.")

	return indicators.dropna()