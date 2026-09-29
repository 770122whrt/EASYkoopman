"""Read-only hull geometry, clearance and contact sensor binding."""
import itertools
import numpy as np
from koopman.physics_context import rotation
from workflows.observation_trace import _copy

def clearance(points, pose_xyzw, ground_z):
    p=np.asarray(points,dtype=float);pose=np.asarray(pose_xyzw,dtype=float)
    if (p.shape!=(8,3) or pose.shape!=(7,) or not np.isfinite(p).all()
            or not np.isfinite(pose).all() or not np.isfinite(ground_z)
            or abs(np.linalg.norm(pose[3:])-1)>1e-3):
        raise ValueError('clearance_geometry_invalid')
    r=rotation(pose[[6,3,4,5]].reshape(1,4))[0]
    return float(np.min((p@r.T+pose[:3])[:,2])-ground_z)


def step_clearance(row,geometry):
    return min(clearance(geometry['body_local_corners_m'],b['transform_actor_world_xyzw'][0],
                         geometry['ground_world_z_m'])
               for b in (row['before']['backend'],row['backend_after_physics']))


def physics_attributes(prim):
    return {a.GetName():str(a.Get()) for a in prim.GetAttributes()
            if 'physics' in a.GetName().lower() or a.GetName().startswith('physx')}


def contact_report_spawner(original,records):
    """Add reporting only. Unlike activate_contact_sensors, never change sleep."""
    def spawn(*args,**kwargs):
        from pxr import Usd,UsdPhysics,PhysxSchema
        prim=original(*args,**kwargs)
        bodies=[p for p in Usd.PrimRange(prim) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
        if len(bodies)!=1:raise ValueError('contact_requires_one_body')
        body=bodies[0];before=physics_attributes(body)
        report=PhysxSchema.PhysxContactReportAPI.Apply(body)
        report.CreateThresholdAttr().Set(0.)
        after=physics_attributes(body)
        without_report=lambda d:{k:v for k,v in d.items() if not k.startswith('physxContactReport:')}
        if without_report(before)!=without_report(after):raise ValueError('contact_modified_mechanics')
        records.append({'body_path':str(body.GetPath()),'before':before,'after':after,
                        'changed_attributes':sorted(k for k,v in after.items() if before.get(k)!=v)})
        return prim
    return spawn


def bind_contact_getter(env,geometry):
    from isaacsim.core.simulation_manager import SimulationManager
    from pxr import PhysxSchema
    import omni.usd
    path=geometry['body_path'];body=omni.usd.get_context().get_stage().GetPrimAtPath(path)
    if not body.HasAPI(PhysxSchema.PhysxContactReportAPI):raise ValueError('contact_report_not_authored')
    view=SimulationManager.get_physics_sim_view().create_rigid_contact_view(path)
    paths=list(view.sensor_paths)
    if paths!=[path] or view.sensor_count!=1:raise ValueError('contact_view_body_binding')
    dt=float(env.sim.cfg.dt)
    def read():
        return {'normal_force_world_n':_copy(view.get_net_contact_forces(dt=dt)),
                'body_paths':paths,'physics_dt_s':dt,
                'sample_timestamp_s':float(env._robot.data._sim_timestamp),
                'quantity':'net_normal_contact_force_world_n_not_total_friction_force'}
    return read

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
