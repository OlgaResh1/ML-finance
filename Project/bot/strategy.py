 
import pandas as pd
import logging

logger = logging.getLogger(__name__)

BUY = 1
SELL = -1
HOLD = 0

def generate_signal(indicators: pd.DataFrame, predictions: pd.DataFrame | None) -> int:

    if indicators.empty:
        logger.warning("Cannot generate signal: Indicators DataFrame is empty.")
        return HOLD
    if predictions is None or predictions.empty:
        logger.warning("Cannot generate signal: Model predictions are missing.")
        return HOLD 

    try:
        last_indicators = indicators.iloc[-1]
        last_prediction = predictions.iloc[-1]

        cmf_signal = last_indicators['CMF_20_Positive']
        di_cross_signal = last_indicators['DI_Cross_14']
        stoch_cross_signal = last_indicators['Stochastic_Cross_5_5']
        model_signal = last_prediction['Pred_Direction']
        
        tech_agree_bullish = (cmf_signal == 1 or di_cross_signal == 1 or stoch_cross_signal == 1)
        should_buy = tech_agree_bullish and (model_signal == 1)

        if should_buy:
            logger.info(f"Signal: BUY (Tech Bullish: {tech_agree_bullish}, Model Up: {model_signal == 1})")
            return BUY
        else:
             logger.info(f"Signal: HOLD/EXIT (Tech Bullish: {tech_agree_bullish}, Model Up: {model_signal == 1})")
             return HOLD 

    except KeyError as e:
        logger.error(f"Missing column for signal generation: {e}")
        return HOLD
    except IndexError:
        logger.error("Not enough data in indicators/predictions for signal generation.")
        return HOLD
    except Exception as e:
        logger.error(f"Error generating signal: {e}")
        return HOLD