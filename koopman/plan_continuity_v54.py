"""Retain an active plan when a replacement reply is rejected.

Retention is not admission: inherited choose() still checks the active plan's
identity, acknowledged history, wall/index age and current-state deviation on
every use. Explicit fallback/worker-fault invalidation continues to clear both.
"""
from koopman.plan_arbiter_v52 import PlanArbiter as PreviousArbiter
from koopman.runtime_coordinator_v52 import RuntimeCoordinator as PreviousCoordinator


class PlanArbiter(PreviousArbiter):
    def ingest(self,event):
        active=self._active
        result=super().ingest(event)
        if result['status']=='rejected':
            # Only the replacement lost admission. Never restore its prefix or
            # pending slot, and never skip independent active-plan validation.
            self._active=active
        return result


class RuntimeCoordinator(PreviousCoordinator):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.arbiter=PlanArbiter(self.ledger,config=self.arbiter.config,clock=self.clock)
