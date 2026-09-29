"""Keep the frozen NLP/objective; only tighten deadzone bounds explicitly."""
from koopman.continuous_mpc_v76 import ContinuousMPC as PreviousMPC
from koopman.preview_solver_v80 import tighten_deadzone_bounds,enforce_interior


class ContinuousMPC(PreviousMPC):
    def _build(self):
        super()._build()
        self._lower_g=tighten_deadzone_bounds(self._lower_g,self.horizon,
                                             self.plant.allocator.wrench_matrix.shape[1])

    def check(self,origin,state,commands,previous,reference):
        checked=super().check(origin,state,commands,previous,reference)
        return enforce_interior(checked,self.plant.allocator,commands)
