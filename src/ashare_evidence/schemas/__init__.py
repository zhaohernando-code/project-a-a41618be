"""Schema domain barrel — re-exports all Pydantic models."""
from .stock import *
from .portfolio import *
from .simulation import *
from .runtime import *
from .research import *
from .shortpick import *
from .operations import *

# Resolve forward references across domain files. Stock and simulation models
# reference types from operations/simulation that aren't imported at module level
# (circular dependency: stock -> operations -> simulation -> operations).
# After every module is loaded, inject the needed types into the originating
# module namespaces and rebuild the affected Pydantic models.
import sys

_stock_mod = sys.modules[__name__ + ".stock"]
_sim_mod = sys.modules[__name__ + ".simulation"]

# Choose local names that the modules' string annotations reference
_stock_mod.PricePointView = PricePointView  # from .operations
_stock_mod.SimulationOrderView = SimulationOrderView  # from .simulation

_stock_mod.RecommendationTraceResponse.model_rebuild()
_stock_mod.StockDashboardResponse.model_rebuild()

_sim_mod.PricePointView = PricePointView  # from .operations
_sim_mod.SimulationKlineView.model_rebuild()
_sim_mod.SimulationTrackStateView.model_rebuild()
