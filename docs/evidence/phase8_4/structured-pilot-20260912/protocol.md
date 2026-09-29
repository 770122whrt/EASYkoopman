# Frozen structured-input hypothesis pilot

2026-09-12, frozen before collection/fitting. Plan03 tests the new known-input identifiability hypothesis;02 remains NO_GO. User's continuinggoal anddelegatedroutineimplementation authorization apply. No formalD-23 ormodelhandoff is created.

## Data and resource contract

Same immutable r7plant/source`b87ce2047ee828424094d0a307383694cec79adf`, lockedIsaacSim5.0/IsaacLab2.2.1/RTX4090. Newcheckout `/root/EASYkoopman-phase8-4-structured-20260912` andtransfernamespace`structured-r7`; results `structured-<configuration>-<seed>-<family>`. No source editingintheruntimecheckout. Analysisv25sourcehashedseparately beforefit.

Exactlybase/uuv4/uuv6×6episodes×128controlintervals=2304intervals/4608physicsrows. Directpre-TAM4Dhold,2physicsticks/control,physicsdt1/120; amplitudes[.04,.04,.08,.2],PRBShold4, existingdeterministicmultisine/chirpformulas. Singleenvironment,authored_static_v1/declared_v1/episode_local_v1,knownzeroactuators,nofluid/noise/DR/faults. Samegeometry/masks/bounds. All18episodesfresh:

| Role | Seed | Family |
|---|---:|---|
| fit |8431|PRBS|
| fit |8432|multisine|
| fit |8433|chirp|
| validation |8441|PRBS|
| validation |8442|multisine|
| validation |8443|chirp|

Onebatch,10minutes/process,120minutes/batch,stopfirstnative/source/semanticfailure; noautomaticrepeat. Source/runtime/mechanics/token/clock/reset/rowcount/loadpath/inventory/hash/pullback mustpass beforefit. Knownfloat32clock,command/PWMreconstruction1e-6,speed/wrench1e-3. No filtering/survivorselection. Priorpilot8411–8423dataexcludedfromfit/scaling/evaluation; it onlymotivatedthishypothesis.

## Models, fixed before outcomes

Fourfamilies×sevenscopes=**28fits**, nosearch:

- `linear_free`, `nonlinear_free`: originalv24fullcontrolledEDMD with freelylearnedphysical6Dinputmatrix.
- `linear_fixed`, `nonlinear_fixed`: v25knownexplicitdtIvelocitykick; removeitsfullnonlinearliftincrementfromtargets andfitremainingfullstate-liftincrementfromstatefeaturesalone. Atprediction addknownliftedkick. No learnedforcecoefficients. Exactformulas in[structuredspec](08.4-STRUCTURED-INPUT-SPEC.md).

Sevenscopes:3configuration-local,1pooledall3,3source-onlyheldout2→thirdconfiguration. Fit-onlynormalizersfromwholefitepisodes;meanridge.001,std floor1e-6,SVD,unpenalizedintercept,condition<=1e8; preserveallcoefficients/rank/singularvalues/fitmatrixhashes. Noeigenvalueclipping/stabilityretuning/featuredeletion/configurationID/PCA. Same25/58dictionaries andknownphysicalcontextforallmodels. Per-configurationbackendmass/inertia knownatprediction; inputcomputedfromcandidatecommandsandownNrotorhistory,neverfutureforce/speedtruth.

Bothmainfree/fixedvariantsuseidenticalknowncurrent-twistposeupdateandrelifting. Forbothnonlinearvariants, reuseeachoperatorinanunprojected-liftablation;freev24haslinear liftedrecursion, fixedv25stillhasnonlinearknownkickcomputedfromdecodedcurrentstate. Thus neitherablationlicensesattributingallgainstolinearKoopmanclosure. Noextraablationfits. Persistencehasnofit.

Physicsdriftisnotinjected, onlydirectinputkick; same-informationlinear_fixedisolatesnonlinearliftbenefit. A whollyanalyticfluidmodelisnotbeingclaimedaslearning. Thekickisanexplicitfinite-stepapproximation;03A'smeasurednextorientation/totalwrenchdiagnosticisnotapredictorinput.

## Scores and frozen gates

Everyvalidationepisode: allcontrol-boundarysliding1/20/60controlhorizons andfixedorigin128. Eachpathincludeseveryphysicsstep. State11/physicalerrorunitsandquaternionSO3geodesic unchanged. Depth/linear/angularcomponentabs>100,nonfiniteorinvalid/degeneratequaternion/R6failsorigin;anyfailureinvalidatesthecompleteepisode/horizonaggregate. Reportfailedorigincounts andfirstfailureticks. Fullmacroabsentifanymandatoryepisodefailed;neveraverageonlysurvivors.

Engineeringcomparisonfloor.01foreachdepth/attitude/linearvelocity/angularvelocityunit. Equalconfiguration/seedweight. Forboth20and60andbothendpoint/path, primarysource-onlyheldout **nonlinear_fixed** must:

1. Have9/9completeaggregates and9/9stable128rollouts, allcorrectness/numericgatespass.
2. Mean`candidate/max(persistence,.01)`<=1.05; eachconfigurationmean<=1.05; eachphysicalmetricmean<=1.10. Meanlinear+angularvelocityratio<=.90, directionbetterthanpersistencecomparisonin>=2/3seedsforeveryconfiguration.
3. Haveacompletesame-information`linear_fixed`comparator; candidatenormalizedmacro<=.90×linearfixednormalizedmacroandnoindividualconfigurationratio>1.05. This is the nonlinear-liftinvestmentgate.

The newstructuralrepairmechanism also requiresanalytically/testedzero learnedforcecrossgains andcorrectknownkickunits. `free` variants arediagnosticbaselinefailures: reportallpairedfiniteerrors,coverageandfailurecounts. If freebaselinefails, itsfinite-errorimprovementpercentageis**unavailable**, notanautomaticnumericalwin. It isnotamandatorycompletecomparatortoqualifythenewstructure;this distinctionisfixedbeforeoutcomes because thehypothesistargetsits observedunidentifiability. Thereisnostatementthatanunavailablecomparisonpassedold02'sgate.

GOrequiresall3primarygatesaboveandmechanical/sourcecorrectness. Candidatefailureorthresholdfailure→NO_GO; missinglinearfixedfinitecomparisonwithoutanothermandatoryfailure→INCONCLUSIVE. Recordinput/statecoverage andknowncataloglimitations; thissmalltestcannotprovideformaluncertainty,unseenplatform,512step,closedloop,Agenticorhardwareclaims.

OnlyGOpermitsdraftingaconcreteformalD-23fortheuser'sdecision. Ifitfails, preservetheresultanddiscussthenextscientificscope/assumption; noautomaticadditionalmodel/dataexperimentunderthisprotocol. Prior02scoresarenotchanged.
