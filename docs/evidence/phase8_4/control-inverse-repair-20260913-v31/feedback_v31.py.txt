"""Same causal demand, bounds and acceptance; repaired failed-branch inversion."""
from workflows.feedback_v28 import target_terms,validate_decision,parameters as prior_parameters
from workflows.workpoint_v27 import mechanics
from workflows.feedback_inverse_v31 import solve_feasible_control

def parameters():
    p=prior_parameters();p['inverse_refinement']='all_controllable_axes_branch_seeds_and_post_crossing_refinement_v31';return p

class FeedbackPolicy:
    def __init__(self,name):self.name=name;self.mechanics=mechanics(name)
    def decide(self,state_available,excitation):
        terms=target_terms(state_available,excitation,self.name)
        allocation=solve_feasible_control(self.name,terms['target_wrench_6_n_nm'])
        return dict(terms,command_4=allocation['command_4'],allocation=allocation)
