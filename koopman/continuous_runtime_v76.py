"""Synchronous simulation-time MPC with the existing execution/safety ledger.

Physics does not advance while solving. This interface cannot establish real
time operation. Only the first command is dispatched, with four actual receipts.
"""
import time
import numpy as np
from koopman.runtime_coordinator_v52 import RuntimeCoordinator, RuntimeConfig
from koopman.rate30_v67 import Progress30


class ContinuousCoordinator(RuntimeCoordinator):
    def __init__(self, ledger, feedback, solver=None):
        config=RuntimeConfig(control_compute_budget_s=60., no_improvement_controls=30,
                             zero_progress_controls=15)
        super().__init__(ledger, feedback, config=config)
        self.progress=Progress30(ledger._domain.configuration, config=config)
        self.solver=solver
        self.solve_audit=[]

    def step(self, observation, reference, *, reference_id, safety):
        started=time.perf_counter()
        try:
            if self.ledger.stopped:return self._stop(self.ledger.stop_reason)
            self._safety(safety,observation.episode_id,observation.reset_id,observation.physics_index)
            cap=self.ledger.capture(observation,reference,reference_id=reference_id)
            progress=self.progress.observe(cap.physics_index//2, cap.state, cap.reference,
                reference_id=reference_id,last_tracking=self._last_tracking)
            if progress['status']=='stop':return self._stop(progress['reason'])
            feedback=self.feedback.decide(cap.state,cap.reference,previous=cap.previous)
            if feedback['status']!='ready':return self._stop('feedback_'+str(feedback.get('reason')))
            command=feedback['command'];source='fallback';status='feedback'
            tracking={k:feedback.get(k) for k in ('tracking_status','zero_progress')}
            if self.solver is not None and cap.previous is not None:
                baseline=np.tile(command,(self.solver.horizon,1))
                result=self.solver.solve(origin=cap.origin, initial_state=cap.state, baseline=baseline,
                    previous=cap.previous, reference=cap.reference)
                self.solve_audit.append(dict(physics_index=cap.physics_index, **result))
                self.stats['requests']+=1
                if not result['exact_feasible']:
                    return self._stop('continuous_no_exact_plan:'+str(result['reason']))
                command=result['commands'][0];source='mpc';status=result['status']
                # An exact feasible baseline may be retained, but it is not an
                # optimized activation or evidence of a model/controller gain.
                if status!='baseline_retained':self.stats['mpc_activations']+=1
                tracking=None
            elapsed=time.perf_counter()-started
            if elapsed>=self.config.control_compute_budget_s:return self._stop('continuous_decision_budget')
            ticket=self.ledger.reserve(cap,command,source=source,startup=cap.previous is None)
            packet=self.ledger.dispatch(ticket)
            self._pending_info=dict(tracking=tracking,compute_s=elapsed,ticket=ticket)
            self.stats['dispatches']+=1
            return dict(status='dispatch',reason=None,packet=packet,progress=progress,
                solver_status=status,decision_compute_ms=elapsed*1000,actual_history_advanced=False,
                timing_mode='synchronous_nonrealtime')
        except (ValueError,RuntimeError,TypeError,KeyError,AttributeError,FloatingPointError) as exc:
            return self._stop('continuous_decision_failed:'+str(exc))
