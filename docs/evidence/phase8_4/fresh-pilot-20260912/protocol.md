# Frozen fresh pilot protocol — projected controlled EDMD with causal actuation

Frozen before pilot collection or fitting,2026-09-12. This is one bounded exploratory investment experiment, not formalD-23. Source seam gate has passed: three original/direct-sequence pairs andbaseholdon/off are exact over observed state/control/wrench. Phase8.2 and8.3data are excluded from this fit/scaling/evaluation.

## Dataset and operation

One plant variant: `direct_pre_tam_v24`, authored_static_v1, declared_v1, episode_local_v1; single environment, no disturbances/sensor noise/DR/faults, fixed configuration through creation/reset/run. Physicsdt1/120,decimation2,control1/60. Full two-substep trace and known-zero rotor initialization. Eachphysics row must bind currentstate, actually sent boundedcommand, actuator update and nextstate; preserve command-frame/physical-force distinction.

| Role | Seed | Family | Amplitudes [roll,pitch,yaw,depth] | PRBS hold |
|---|---:|---|---|---:|
| fit |8411|PRBS|[0.04,0.04,0.08,0.20]|4|
| fit |8412|multisine|same|4(unused)|
| fit |8413|chirp|same|4(unused)|
| validation |8421|PRBS|same|4|
| validation |8422|multisine|same|4(unused)|
| validation |8423|chirp|same|4(unused)|

Exactlybase/uuv4/uuv6×6wholeepisodes×128controlintervals=2304intervals/4608physics transitions. uuv4yawcommand masked before allocation; unactuated yaw tracking is not a feasible control objective, but actual coupled yaw velocity is still part of dynamics prediction. Multisine/chirp formulas are the tested `pilot_control_v24.commands` source:0.7/2.3Hz weighted0.6/0.4 sine;0.3→3Hz chirp; seeded independent phases. No changes after output inspection.

Use tested source snapshot`71c4cdda16dac2b35c5d158f11f1c3eb084e10b2` for unchangedcollection, newrequest/result IDs `pilot-<configuration>-<seed>-<family>`. Separatetransferlogs; no overwrite of8.4seamresults. Eachprocess10min,total120min, onebatch; stop on first native/source/bounds/reset/clock/trace failure. Same lockedIsaac runtime, source hashes, exits, exact inventory/archive/pullback gates. GPUphysics; smallSVDfit staysCPU. No grid or automaticpilotrepeat.

## Causal plant representation

Maintain completeNrotor speed from knownzero and plannedcommands. Everyphysics tick computes rawallocation→clippedPWM→nonlinear speed command→laggedrotor state→geometry-derived bodywrench. Use exact configuration geometry/order andmass/inertia; no anonymous rotor-slotpadding. RuntimePWM is known commandedinput, actualrotor/wrench values are validation-only. Futurecontrol effects are computed from candidate/presetcommands and ownactuatorhistory, never futuremeasuredphysicalstate. Initialstate for slidingorigins is measured; inputhistory is reconstructed once fromepisodezero without truthfeedback.

Two model-input representations on identicaltransitions andsameclock:

- `physical`:6D predictedbodywrench divided by actualmass/diagonalinertia, after eachcausalactuatorupdate. FullNmemory remains inside theactuator module; this is not a claim that one netwrench replaces itsstate.
- `proxy`:4Dheldcommand plus4DcausalEMA atphysicsdt withsameknownτ/mask. This is the information-ablation; noactualforce/rotor data enters it.

Check reconstruction beforefit: virtual/PWMabs<=1e-6, speedabs<=1e-3, thrusterwrenchabs<=1e-3; if failed, no model scores. Report deadzone/saturation, unique commands, state ranges and realized mechanics. No saturation/coverage filtering ofrows after observation.

## Fixed lifted dictionaries and operators

State remains11D:worldz,wxyz body-to-world quaternion,bodyv,bodyω. Finite state features always begin with13coordinates `[z,R6,v,omega]`, using existing R6 column order. Bodyup isRᵀ[0,0,1]. Knowncontext is configured/validatedmass,I,volume,COBoffset,dragmultiplier,waterdensity/viscosity; no configurationID,PCA,globalstatistics or learned heldoutdescriptor.

`linear` dictionary (25nonbias features):13basecoordinates plus3netbuoyancy acceleration,3buoyancy moment/inertia,6linearviscous acceleration. These terms are linear invelocity orrotation entries for fixedcontext. Context factors use the implemented equivalent-inertia-box geometry and validatedmechanics; this is a structured baseline, not raw globally constant coefficients.

`nonlinear` dictionary (58nonbias features):alllinearfeatures plus6quadraticdrag accelerations,3omega×v transport terms,3(omega×Iomega)/Iterms,18R6×omega terms,3world-z-row rotation×bodyvelocity products. The force formulas are source-derived physical observables, not known drift coefficients injected into the learned state update. No hiddenadded-mass dynamics is assumed: this simulator's active hydrodynamic methods are stateless buoyancy/quadraticdrag/linearviscosity. Fossenmotivates the separation but does not certify this simulator's physics.

Fit a full controlled EDMDincrement operator for each dictionary, not only a renamed plainlinear state model: predict all nextobservable coordinates. Center/scale observable andinput columns using fitdata only,std floor1e-6; fit mean-squared ridge1e-3 bySVD, unpenalizedintercept. Targets are scaledobservable increments; algebraically`z_next=z+W*[1,z,normalized_input]`. No contraction/clipping/eigenvalueediting,adaptivefeaturedeletion or hyperparametersearch. Log centeredrank,singularvalues,regularizedcondition (reject>1e8),coefficient/fitrow hashes andcontextbindings.

Primaryrollout is **projected EDMD with known pose kinematics**:applylearnedoperator,read predictedv/omega, advance pose withthe existing current-statebodytwist first-orderdepth andbody-right quaternion exponential atphysicsdt, then re-lift the predictedphysicalstate. Bothlinear/nonlinearmodels use identicalposeupdate. This projection makes the completepredictor nonlinear; do not claim a globallyclosedfinite Koopman invariantspace or an end-to-endlinearQP MPC. An `unprojected_lift` ablation of the samephysicalnonlinearoperator propagatesalllifted coordinates withoutre-lifting; decodeposefrompredictedR6 withorthonormalization, rejectdegeneratecolumns. The fulloperator is preserved and itsclosure/residuals reported; projection's contribution must be distinguished from lifting.

Exactly21fits: threefamilies(`linear_physical`,`nonlinear_physical`,`nonlinear_proxy`)×seven scopes(threeconfiguration-local,onepooledall3,threeheldoutsource2). Every scope uses only its wholefit episodes forfitting/scaling. Primaryscientificpilot score is thethreeheldoutsource2models ontheirheldoutvalidationepisodes; per-config andpooledvalidation diagnose interpolation versus transfer. Theheldoutcase is a knowncatalogmember,not an unseen-platform claim. Unprojectedablation reusesnonlinearphysicalfits; persistence haszero fits. No additionalmodel family or grid.

## Evaluation and decision

Allsliding1/20/60controlinterval horizons use2/40/120physicalsteps. Alsofixedorigin128controlinterval rollout. ComparedepthRMSE(m),SO(3)geodesicRMSE(rad),bodylinearvelocityRMSE(m/s),bodyangularvelocityRMSE(rad/s); reportendpoint andpathmetrics, perconfiguration/seed/family andequalconfigurationmacro. Nonfinite,stateabs(z/v/omega)>100,degenerateR6 orinvalidquaternion abortsthat origin andinvalidates itscompleteaggregate. Never average onlysurvivors ascomplete. Do not use intermediateactualstate inrecursiveprediction. No512stepclaim.

Ratios use common engineeringfloors0.01m/0.01rad/0.01m/s/0.01rad/s forcomparisons withnearzeropersistence; retainrawabsoluteerrors. Motion-weightednormalizedmacro is the arithmeticmean ofthe four errorratios, equalweightconfiguration andvalidationseed. Floors do not change rawerrors or failuregates.

PilotGOrequires allcorrectness/numericalgates and every128rolloutstable forprimaryheldoutmodels; at both20and60:

1. `nonlinear_physical` normalizedmacro<=1.05 relative topersistence, with eachconfiguration<=1.05 and eachindividualphysicalmetric<=1.10 (sameengineeringdenominator).
2. Linear+angularvelocity combinednormalizederror improves>=10%overpersistence; direction agrees foratleast2/3validationseeds.
3. `nonlinear_physical` improvesnormalizedmacro>=10%over `nonlinear_proxy` (representationinvestment) and>=10%over `linear_physical` (nonlinearliftinginvestment), with no configurationdegradation>5%. Useexactpairedoriginsets; anyincompletecounterpart makes thatcomparison unavailable,not anautomaticwin.

These are screeningcriteria,not statisticalsignificance. Missing motion/excitationcoverage orfailedcomparators yieldsINCONCLUSIVE unlessanothermandatorygate alreadyfails; acomplete validcandidate failing thresholds yieldsNO_GO. Report all outcomes, includingwhether onlyprojected/pool/per-config variantswork. No automaticformalcollection. OnlypilotGO permits preparing a concrete newD-23protocol foruserdecision; Phase9stillneedsformalqualifyinghandoff. Newresearchbudget would require a statedmissinghypothesis andfreshprotocol,not tuning thesevalidationepisodes.

Method references: [Korda/Mezić2018](https://arxiv.org/abs/1611.03537) forcontrolledfinite-dimensional liftedprediction; [Fossen's marinecraftmodel](https://www.fossen.biz/html/marineCraftModel.html) fordistinguishingkinematics,damping,restoring,inertia andinput. Ourprojected/hybrid implementation anditslimitations areexplicitabove; neitherreference proves itsperformance.
