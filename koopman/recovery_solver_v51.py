"""v50 integration with deadzone-aware candidate admissibility.

Model loading, baseline construction, final recheck and request binding are
unchanged. Retain v50's rejection evidence rather than rewriting its result.
"""
from koopman.bounded_mpc_v51 import BoundedMPC
from koopman.recovery_solver_v50 import RecoverySolver as PreviousRecoverySolver
from koopman.recovery_solver_v50 import frozen_model_factory as previous_factory


class RecoverySolver(PreviousRecoverySolver):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        old=self.solver
        self.solver=BoundedMPC(self.domain,old.predictor,model_id=self.domain.model_id,
            config=old.config,weights=old.weights,allow_diagnostic=kwargs.get('allow_diagnostic',False))


def frozen_model_factory(spec):
    prepared=previous_factory(spec)
    return RecoverySolver(prepared.domain,prepared.baseline.context,prepared.solver.predictor,
        config=prepared.config,feedback_config=prepared.baseline.config,weights=prepared.solver.weights)
