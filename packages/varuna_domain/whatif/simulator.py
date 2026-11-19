from varuna_contracts.schemas import ForwardForecast
from varuna_chhaya.protocol import ChhayaProvider
from typing import Any

class WhatIfSimulator:
    def __init__(self, chhaya_service: ChhayaProvider):
        self.chhaya_service = chhaya_service
        
    def simulate_wind_change(self, forecast: ForwardForecast, detection: Any, wind_speed_multiplier: float) -> ForwardForecast:
        # Stub: just return the same forecast with modified trajectory_path
        new_forecast = self.chhaya_service.forecast(detection, None)
        new_forecast.trajectory_path = forecast.trajectory_path + f"_wind_x{wind_speed_multiplier}"
        return new_forecast
