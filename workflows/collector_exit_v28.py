"""Keep collection failures authoritative after SimulationApp cleanup."""


def cleanup_preserving_failure(failure, callbacks):
    first = failure
    for close in callbacks:
        try:
            close()
        except SystemExit as exc:
            if exc.code not in (None, 0) and first is None:
                first = exc
        except BaseException as exc:
            if first is None:
                first = exc
    if first is not None:
        raise first.with_traceback(first.__traceback__)


def guarded_exit_code(native_exit, report, request, source):
    """A parent without SimulationApp retains both native and semantic status.

    SDK native shutdown may terminate Python before a pending raise executes.
    This small guard is not the full trace validator; the runner still performs
    independent physics/source/causal acceptance after a completed collection.
    """
    if native_exit:
        return native_exit if native_exit > 0 else 128-native_exit
    if (not isinstance(report, dict)
            or report.get('status') != 'completed_calibration_pending_acceptance'
            or report.get('request') != request or report.get('source_commit') != source
            or report.get('training_eligible') is not False or report.get('model_fits') != 0):
        return 1
    return 0
