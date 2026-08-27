class Sentinel1Preprocessor:
    """Stub for Sentinel-1 specific preprocessing (e.g. SNAP integration)."""
    def preprocess(self, raw_path: str) -> str:
        # In reality, this would orchestrate SNAP or similar tools to apply orbit files,
        # thermal noise removal, calibration to sigma0, and terrain correction.
        return raw_path
