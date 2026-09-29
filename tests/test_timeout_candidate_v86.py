"""A solver timeout is not convergence, but must not discard its last iterate."""
import numpy as np
import pytest

pytest.importorskip('casadi')
from test_continuous_mpc_v76 import setup


@pytest.mark.parametrize('status', ['Maximum_CpuTime_Exceeded', 'Maximum_WallTime_Exceeded'])
@pytest.mark.parametrize('candidate', ['finite', 'infeasible', 'nonfinite'])
def test_timeout_preserves_candidate_and_independently_checks_it(status, candidate):
    solver, live, args = setup()
    answer = args['baseline'].copy()
    if candidate == 'infeasible':
        answer[0, 3] = .8
    elif candidate == 'nonfinite':
        answer[0, 3] = np.nan

    class TimedOut:
        def __call__(self, **kwargs):
            return {'x': answer[:, solver.axes].T.reshape(-1, order='F'),
                    'g': np.zeros_like(solver._lower_g)}

        def stats(self):
            return dict(return_status=status, success=False, iter_count=4)

    solver._solver = TimedOut()
    result = solver.solve(**args)
    assert result['solver']['return_status'] == status
    assert result['solver']['success'] is False
    assert result['solver']['timed_out'] is True
    assert result['exact_feasible'] is True  # Independently checked baseline survives.
    assert result['selected_source'] == 'baseline'
    assert live.physics_index == 16
    if candidate == 'nonfinite':
        assert result['candidate_commands'] is None
        assert result['candidate_failure'] == 'nonfinite_or_invalid_shape'
    else:
        np.testing.assert_array_equal(result['candidate_commands'], answer)
        assert result['solution_check']['feasible'] == (candidate == 'finite')
        assert result['constraint_violation'] >= 0
        assert result['command_bound_violation'] >= 0


def test_timeout_without_returned_iterate_does_not_invent_one():
    solver, _, args = setup()
    class Broken:
        def __call__(self, **kwargs):
            raise RuntimeError('external interruption')
    solver._solver = Broken()
    result = solver.solve(**args)
    assert result['candidate_commands'] is None
    assert result['status'] == 'no_plan'
    assert not result['exact_feasible']


def test_real_ipopt_cpu_timeout_retains_and_checks_finite_iterate():
    solver, _, args = setup()
    solver.solve_seconds = 1e-9
    solver._build()
    result = solver.solve(**args)
    assert result['solver']['return_status'] == 'Maximum_CpuTime_Exceeded'
    assert result['candidate_commands'] is not None
    assert np.isfinite(result['candidate_commands']).all()
    assert 'solution_check' in result and result['exact_feasible']
    assert result['solver']['success'] is False
