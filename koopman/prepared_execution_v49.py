"""Use the source-equivalent prepared allocation for real acknowledged history.

Only the static command map changes. Sequencing, transactional recurrence,
float32 clock, snapshots and v48 issuance checks retain their original code.
"""
from koopman.command_state_v39 import CausalCommandState
from koopman.execution_ledger_v48 import ExecutionLedger
from koopman.prepared_allocation_v42 import PreparedDirectAllocation


class PreparedCausalCommandState(CausalCommandState):
    def __init__(self, configuration, context, *, episode_id, zero_rotor_reset_verified):
        super().__init__(configuration, context, episode_id=episode_id,
                         zero_rotor_reset_verified=zero_rotor_reset_verified)
        # Initialization above owns the unchanged tau, channel count and clock.
        # record_issued only consumes command(...)["pwm"], not old PID diagnostics.
        self._kernel = PreparedDirectAllocation(configuration)


class PreparedExecutionLedger(ExecutionLedger):
    def __init__(self, domain, context, reset, **kwargs):
        super().__init__(domain, context, reset, **kwargs)
        # Before the instance is published, history is still the verified zero origin.
        self._live = PreparedCausalCommandState(domain.configuration, self._context,
            episode_id=reset.episode_id, zero_rotor_reset_verified=True)
