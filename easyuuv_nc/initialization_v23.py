"""Opt-in static mechanical initialization before PhysX creates the rigid body."""
import math


def initial_mechanics(cfg):
    mode = getattr(cfg, 'physics_initialization_mode', 'legacy')
    if mode == 'legacy':
        return None
    if mode != 'authored_static_v1':
        raise ValueError('physics_initialization_mode_invalid')
    if cfg.inertia_sync_mode != 'declared_v1':
        raise ValueError('static_initialization_requires_declared_inertia')
    if cfg.domain_randomization.use_custom_randomization:
        raise ValueError('static_initialization_does_not_support_domain_randomization')
    name = cfg.initial_embodiment_type
    if name not in cfg.embodiment_configs:
        raise ValueError('initial_embodiment_unknown')
    source = cfg.embodiment_configs[name]
    mass = float(source['mass'])
    diagonal = [float(v) for v in source['inertia_tensors']]
    if len(diagonal) != 3 or not all(math.isfinite(v) and v > 0 for v in [mass, *diagonal]):
        raise ValueError('initial_mechanics_invalid')
    return {'configuration': name, 'mass_kg': mass, 'inertia_diagonal_kg_m2': diagonal}


def author_initial_mechanics(cfg, sim_utils):
    """Author only the live stage, after spawning and before cloning/physics init.

    This does not edit the source USD, advance physics, or flush the simulator.
    Catalog diagonal inertias use the actor axes and COM remains unchanged.
    """
    mechanical = initial_mechanics(cfg)
    if mechanical is None:
        return None
    from pxr import Gf, UsdPhysics
    template = sim_utils.find_first_matching_prim(cfg.robot_cfg.prim_path)
    if template is None:
        raise RuntimeError('initialization_rigid_prim_missing')
    bodies = sim_utils.get_all_matching_child_prims(
        template.GetPath().pathString, predicate=lambda prim: prim.HasAPI(UsdPhysics.RigidBodyAPI))
    if len(bodies) != 1:
        raise RuntimeError('initialization_requires_one_rigid_body')
    mass_api = UsdPhysics.MassAPI.Apply(bodies[0])
    before = {'mass_kg': mass_api.GetMassAttr().Get(),
              'inertia_diagonal_kg_m2': list(mass_api.GetDiagonalInertiaAttr().Get())}
    mass_api.CreateMassAttr().Set(mechanical['mass_kg'])
    mass_api.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(*mechanical['inertia_diagonal_kg_m2']))
    mass_api.CreatePrincipalAxesAttr().Set(Gf.Quatf(1.0))
    actual = [mass_api.GetMassAttr().Get(), *mass_api.GetDiagonalInertiaAttr().Get()]
    expected = [mechanical['mass_kg'], *mechanical['inertia_diagonal_kg_m2']]
    if any(not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-7) for a, b in zip(actual, expected)):
        raise RuntimeError('initialization_authored_readback_mismatch')
    return {**mechanical, 'original_asset_mechanics': before,
            'rigid_prim_path': bodies[0].GetPath().pathString,
            'principal_axes_wxyz': [1., 0., 0., 0.], 'extra_physics_steps': 0}
