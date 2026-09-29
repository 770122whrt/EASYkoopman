"""Predeclared single-factor development profiles, shared by both MPC models."""
from koopman.control_objective_v44 import ObjectiveWeights

PROFILES=('repair','depth4','depth4_h20')


def settings(profile):
    if profile not in PROFILES:raise ValueError('unknown_v77_profile')
    return dict(horizon=20 if profile=='depth4_h20' else 10,
                weights=ObjectiveWeights(depth=1. if profile=='repair' else 4.))
