# Structured-input EDMD design

2026-09-12, before structured-model fitting. This is03B of the delegated research route. Prior02models andNO_GO stay frozen.

## What changes

Retain the original state11,25/58dimensional dictionaries, causalN-rotor recurrence,4Ddirectholdandphysicsdt. Replace the freely learned six-dimensional physical input matrix with a known input increment. The remaining state operator still predicts all lifted observables.

For physical input `a=[F_body/m, M_body/I]`, define a known **explicit approximation** `kick(x,a)` that preserves pose and adds`dt*a` tobodyvelocity. Let`phi`be the chosen dictionary. Fit

`phi(x_next)-phi(x)-[phi(kick(x,a))-phi(x)]`

fromstatefeatures`phi(x)`alone, withfixedfit-onlycentering/scaling andmeanridge.001. Thus the learned state increment contains no free force coefficients. At prediction, add back the same known lift increment. In projected rollout, use predictednu and the existing current-twistpose update, thenrelift. Conditional onthe same currentstate, aone-tick change inFx/m cannot create a learned arbitraryvz cross-gain; the directnu input increment is dtI byconstruction.

The complete model is a **structured controlled lift plusknownnonlinearinput map andprojection**, not a constantA/B globallylinear MPCplant. Higher-orderliftedinput changes are nonlinear; the pose projection remains nonlinear. Unprojectedablation propagates thelearnedlift withoutrelifting, butdecodesits currentbasecoordinates tocompute the knownkick; it stillcontains nonlinear knowninputphysics. Explicitly label that remainingnonlinearity.

## Why the approximation is acceptable to test, not exact

03A checked4608acceptedphysicsrows withoutfitting. Usingloggedtotalwrench andmeasurednextattitude, translation matchesactualnextbodyvelocity within8.724e-8m/s. This is adiagnostic withfuturetruth, not adeployableprediction. FullyexplicitbodyEulertranslation includingtransport differs byup to3.516e-4m/s; explicitgyroscopicEuler differs byup to6.820e-4rad/s. Actualasset enablesgyroscopicforces. Therefore dtI describes theknowninstantaneousinput term; it isnot exactfullPhysXfinite-stepdynamics. The learnedremainingstate evolution andnewvalidationmust expose approximationerror. No totalmeasuredwrench ornextattitude enters modelinputs.

This design injects onlydirectinputphysics, not acomplete analyticbuoyancy/drag drift. Linearandnonlinearvariants receiveidentical knowninputphysics andposeupdate; theirdifference isolates nonlinearlift choicewithinthishybridarchitecture. Theexistingphysicalobservables carrycontext inboth.

## Interfaces and checks

- Newmodule `koopman/structured_edmd_v25.py`; keep originalv24operatorunchanged.
- Stateless knownkick andliftedkick helpers; fixedstate-onlyoperator withread-only normalizers/coefficientarrays. No model API accepts futuretruth.
- Tests: inputkickunits/channelindependence, exactlyzero learnedforcecrossgain despiteunexcitedfitcontrols, fixedmeanridgeequation,fit-onlynormalizerimmutability, invalidshape/nonfinitefailclosed, projectedrollout causality andbounds.
- Evaluation uses thetestedall-control-origin path/endpoint scorer withanexplicitv25advanceinterface; preserveallfailures.

## Experimental boundary

No fitting on02validation. Freeze a separateprotocol withfresh8431–8443seeds, sameplant, fourfixedfamilies (free/fixedinput × linear/nonlinearlift), sevenpredeclaredfit scopes,28fits. Compareprimaryheldoutnonlinearfixedagainstpersistenceandsame-informationlinearfixed. Freelylearnedinputmodelsare diagnosticcontrols; iftheyfail, reportfailureandunavailablefiniteerrorratio, not anautomatic numericalwin. Reportknowncatalogsource-onlyversuspooled/local separately. NewformalD-23stillrequiresaconcretedecisionafterqualifyingevidence.
