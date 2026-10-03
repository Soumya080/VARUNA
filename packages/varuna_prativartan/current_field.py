"""
VARUNA GRID — Current and Wind field definitions.
"""
from __future__ import annotations
import abc
import numpy as np
from typing import Tuple

class AbstractCurrentField(abc.ABC):
    """Base class for ocean current fields."""
    @abc.abstractmethod
    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> Tuple[np.ndarray, np.ndarray]:
        """Return (u, v) in m/s at the given locations and time."""
        pass

class AbstractWindField(abc.ABC):
    """Base class for wind fields."""
    @abc.abstractmethod
    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> Tuple[np.ndarray, np.ndarray]:
        """Return (u, v) in m/s at the given locations and time."""
        pass

class SyntheticTruthCurrentField(AbstractCurrentField):
    """
    Truth current field with spatial structure (shear + localized eddy).
    """
    def __init__(self, base_u: float = 0.25, base_v: float = 0.10, shear_rate: float = 0.5, eddy_center: tuple[float, float] = (72.0, 15.0)):
        self.base_u = base_u
        self.base_v = base_v
        self.shear_rate = shear_rate
        self.eddy_center = eddy_center
        
    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> Tuple[np.ndarray, np.ndarray]:
        N = len(lons)
        u = np.full(N, self.base_u)
        v = np.full(N, self.base_v)
        
        # Spatial structure: linear shear based on latitude
        u += self.shear_rate * (lats - self.eddy_center[1])
        
        # Add a localized eddy bump to make it spatially complex
        r2 = (lons - self.eddy_center[0])**2 + (lats - self.eddy_center[1])**2
        envelope = np.exp(-r2 / 0.1) # scale is approx 0.3 degrees
        
        # Eddy velocity components (tangential)
        u_eddy = - (lats - self.eddy_center[1]) * envelope * 2.0
        v_eddy = (lons - self.eddy_center[0]) * envelope * 2.0
        
        u += u_eddy
        v += v_eddy
        
        # Slow temporal rotation
        angle = np.radians(15.0 * np.sin(2 * np.pi * t_hours / 48.0))
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        
        u_rot = u * cos_a - v * sin_a
        v_rot = u * sin_a + v * cos_a
        
        return u_rot, v_rot


class SyntheticModelCurrentField(AbstractCurrentField):
    """
    Model current field with structurally DIFFERENT biases from truth.
    Used by backward ensemble to avoid trivially invertible physics.
    """
    def __init__(self, base_u: float = 0.25, base_v: float = 0.10, shear_rate: float = 0.2, eddy_center: tuple[float, float] = (71.8, 15.2)):
        self.base_u = base_u
        self.base_v = base_v
        self.shear_rate = shear_rate # different shear
        self.eddy_center = eddy_center # eddy is displaced
        
    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> Tuple[np.ndarray, np.ndarray]:
        N = len(lons)
        u = np.full(N, self.base_u)
        v = np.full(N, self.base_v)
        
        # Biased spatial structure
        u += self.shear_rate * (lats - self.eddy_center[1])
        
        r2 = (lons - self.eddy_center[0])**2 + (lats - self.eddy_center[1])**2
        envelope = np.exp(-r2 / 0.15) 
        
        u_eddy = - (lats - self.eddy_center[1]) * envelope * 1.5
        v_eddy = (lons - self.eddy_center[0]) * envelope * 1.5
        
        u += u_eddy
        v += v_eddy
        
        # Temporal rotation with different phase/amp
        angle = np.radians(20.0 * np.sin(2 * np.pi * t_hours / 40.0))
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        
        u_rot = u * cos_a - v * sin_a
        v_rot = u * sin_a + v * cos_a
        
        return u_rot, v_rot


class SyntheticWindField(AbstractWindField):
    """
    Spatially uniform but temporally varying synthetic wind.
    """
    def __init__(self, base_u: float = -6.0, base_v: float = 2.0):
        self.base_u = base_u
        self.base_v = base_v
        
    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> Tuple[np.ndarray, np.ndarray]:
        N = len(lons)
        phase = 2 * np.pi * t_hours / 36.0
        u = np.full(N, self.base_u + 3.0 * np.sin(phase))
        v = np.full(N, self.base_v + 3.0 * np.cos(phase * 0.7))
        return u, v
