import logging

def setup_observability():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
class MetricsTracker:
    @staticmethod
    def record_inference_time(model_name: str, duration_ms: float):
        pass # Stub
        
    @staticmethod
    def increment_error_count(component: str):
        pass # Stub
