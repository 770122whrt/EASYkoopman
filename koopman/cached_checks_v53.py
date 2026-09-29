"""Bounded exact memoization of immutable command-to-PWM/steady-wrench maps.

Current demands, residuals, support, slew, history and deadlines are rechecked.
Only a pure fixed-geometry forward map is cached; no actuator state, prediction
or admission decision is stored here. The original v46/v47/v49/v51 remain intact.
"""
from collections import OrderedDict

import numpy as np

from koopman.bounded_feedback_v46 import PreparedSteadyMap
from koopman.bounded_feedback_v47 import PreparedTrackingMap,TrackingFeedback
from koopman.bounded_mpc_v44 import owned
from koopman.prepared_execution_v49 import PreparedExecutionLedger
from koopman.recovery_solver_v51 import RecoverySolver,frozen_model_factory as previous_factory


class _ExactMapCache:
    def __init__(self,*args,cache_limit=128,**kwargs):
        if type(cache_limit) is not int or not 1<=cache_limit<=512:raise ValueError('map_cache_limit')
        super().__init__(*args,**kwargs)
        self._cache_limit=cache_limit;self._cache=OrderedDict();self._cache_binding=self._binding_token()

    def _binding_token(self):
        a=self.allocator
        return (self.configuration,self.context_key,id(self.scale),id(self.mask),id(a),a.configuration,
            a.rotor_constant,id(a.wrench_matrix),id(a._mask),id(a._sign),id(a._weights),id(a._inverse),
            None if a._inverse is None else a._inverse._version)

    @property
    def cache_size(self):return len(self._cache)

    def evaluate(self,command):
        if self._binding_token()!=self._cache_binding:raise ValueError('map_cache_binding_changed')
        u=np.asarray(command,dtype=float)
        if u.shape!=(4,) or not np.isfinite(u).all() or np.any(np.abs(u)>.95):
            raise ValueError('feedback_command_invalid')
        key=u.tobytes()  # Exact float64 bytes, no rounding or approximate keys.
        if key not in self._cache:
            source=super().evaluate(u)
            self._cache[key]={k:owned(v,v.dtype) if isinstance(v,np.ndarray) else v for k,v in source.items()}
            if len(self._cache)>self._cache_limit:self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        # Preserve caller-owned mutable outputs of the source API.
        return {k:v.copy() if isinstance(v,np.ndarray) else v for k,v in self._cache[key].items()}


class CachedSteadyMap(_ExactMapCache,PreparedSteadyMap):pass
class CachedTrackingMap(_ExactMapCache,PreparedTrackingMap):pass


class CachedTrackingFeedback(TrackingFeedback):
    def __init__(self,domain,context,**kwargs):
        super().__init__(domain,context,**kwargs)
        self.steady=CachedTrackingMap(domain.configuration,context)


class CachedExecutionLedger(PreparedExecutionLedger):
    def __init__(self,domain,context,reset,*,steady=None,**kwargs):
        super().__init__(domain,context,reset,**kwargs)
        mapping=CachedSteadyMap(domain.configuration,context) if steady is None else steady
        if (not isinstance(mapping,(CachedSteadyMap,CachedTrackingMap)) or mapping.configuration!=domain.configuration
                or mapping.context_key!=domain.context_key):raise ValueError('execution_cached_map_binding')
        self._steady=mapping
        self._steady.evaluate(self._startup)  # Pure READY preparation, not an issued command.


class CachedRecoverySolver(RecoverySolver):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.baseline.steady=CachedTrackingMap(self.domain.configuration,self.baseline.context)


def frozen_model_factory(spec):
    prepared=previous_factory(spec)
    return CachedRecoverySolver(prepared.domain,prepared.baseline.context,prepared.solver.predictor,
        config=prepared.config,feedback_config=prepared.baseline.config,weights=prepared.solver.weights)
