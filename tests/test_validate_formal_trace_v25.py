import importlib.util
import pytest


def test_formal_trace_rejects_exploratory_status_without_relabelling():
    assert importlib.util.find_spec('workflows.validate_formal_trace_v25')
    from workflows.validate_formal_trace_v25 import validate_trace
    from workflows.formal_contract_v25 import proposal
    with pytest.raises(ValueError,match='formal_trace_status'):
        validate_trace({'status':'completed_exploratory_v24'},proposal()['entries'][0],'a'*40)


def test_formal_trace_requires_exact_new_case_and_source():
    from workflows.validate_formal_trace_v25 import validate_trace
    from workflows.formal_contract_v25 import proposal
    q=proposal()['entries'][0]
    with pytest.raises(ValueError,match='formal_trace_source_or_case'):
        validate_trace({'status':'completed_formal_v25','request':q,'source_commit':'b'*40},q,'a'*40)
