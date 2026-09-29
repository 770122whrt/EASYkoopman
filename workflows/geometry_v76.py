"""Read actual cuboid hull/portable ground, preserving clearance/contact gates."""
import itertools
import numpy as np
from workflows.free_water_runtime_v26 import clearance, physics_attributes
from workflows.control_trace_v23 import _copy


def ground_top(points):
    p=np.asarray(points,dtype=float)
    if p.shape!=(8,3) or not np.isfinite(p).all():raise ValueError('ground_corners')
    lo=p.min(axis=0);hi=p.max(axis=0)
    expected=np.array(list(itertools.product(*zip(lo,hi))))
    if (any(not np.any(np.all(np.isclose(expected,x,rtol=0,atol=1e-7),axis=1)) for x in p)
            or min(hi[:2]-lo[:2])<10 or hi[2]-lo[2]<=0
            or np.any(lo[:2]>-5) or np.any(hi[:2]<5) or abs(hi[2])>1e-6):
        raise ValueError('ground_not_horizontal_covering_zero_top')
    return float(hi[2])


def read_geometry(env):
    from pxr import Usd,UsdGeom,UsdPhysics,Gf
    import omni.usd
    stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache(Usd.TimeCode.Default())
    path=env._initial_mechanics_v23['rigid_prim_path'];body=stage.GetPrimAtPath(path)
    colliders=[p for p in stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)
               and UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get()]
    own=[p for p in colliders if str(p.GetPath()).startswith(path+'/')]
    ground=[p for p in colliders if str(p.GetPath())=='/World/ground' or str(p.GetPath()).startswith('/World/ground/')]
    if len(colliders)!=2 or len(own)!=1 or len(ground)!=1:raise ValueError('geometry_collision_inventory')
    hull,floor=own[0],ground[0]
    if not all(p.IsA(UsdGeom.Cube) for p in (hull,floor)):raise ValueError('geometry_cube_required')
    if not body.HasAPI(UsdPhysics.RigidBodyAPI):raise ValueError('geometry_body_missing')
    def corners(prim,transform):
        half=float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2
        return [list(transform.Transform(Gf.Vec3d(*v))) for v in itertools.product((-half,half),repeat=3)]
    world_ground=corners(floor,cache.GetLocalToWorldTransform(floor))
    z=ground_top(world_ground)
    points=corners(hull,cache.GetLocalToWorldTransform(hull)*cache.GetLocalToWorldTransform(body).GetInverse())
    if float(UsdGeom.GetStageMetersPerUnit(stage))!=1 or UsdGeom.GetStageUpAxis(stage)!='Z':
        raise ValueError('geometry_stage_units')
    pose=_copy(env._robot.root_physx_view.get_transforms())[0]
    return dict(body_path=path,collider_path=str(hull.GetPath()),ground_path=str(floor.GetPath()),
        body_local_corners_m=points,ground_world_corners_m=world_ground,ground_world_z_m=z,
        meters_per_unit=1.,initial_clearance_m=clearance(points,pose,z),minimum_clearance_m=.1,
        body_physics_attributes=physics_attributes(body),algorithm='actual_USD_cuboid_ground_top_v76')
