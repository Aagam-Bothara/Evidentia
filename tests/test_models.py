"""Tests for core domain models."""

from evidentia.core.models import (
    Citation,
    Claim,
    ClaimConfidence,
    EvidenceSpan,
    ExecutionPlan,
    PlanStep,
    Run,
    RunStatus,
    Source,
    SourceType,
    StepResult,
    StepStatus,
)


def test_run_creation():
    run = Run(query="What is protein folding?")
    assert run.status == RunStatus.PENDING
    assert run.query == "What is protein folding?"
    assert run.id is not None
    assert run.elapsed_seconds is None


def test_plan_step():
    step = PlanStep(
        description="Search arXiv",
        tool_name="arxiv_search",
        tool_input={"query": "protein folding"},
    )
    assert step.tool_name == "arxiv_search"
    assert step.depends_on == []


def test_execution_plan():
    plan = ExecutionPlan(
        steps=[
            PlanStep(description="Search", tool_name="web_search", tool_input={"query": "test"}),
            PlanStep(description="Analyze", tool_name="python_sandbox", tool_input={"code": "1+1"}),
        ],
        reasoning="Search first, then analyze",
    )
    assert len(plan.steps) == 2


def test_claim_with_citations():
    claim = Claim(
        statement="AlphaFold predicts protein structures with high accuracy.",
        confidence=ClaimConfidence.HIGH,
        citations=[
            Citation(
                source_id="src1",
                title="Highly accurate protein structure prediction with AlphaFold",
                authors=["John Jumper"],
                doi="10.1038/s41586-021-03819-2",
            )
        ],
        evidence_spans=[
            EvidenceSpan(
                source_id="src1",
                text="AlphaFold predicts protein structures with an accuracy...",
            )
        ],
    )
    assert claim.confidence == ClaimConfidence.HIGH
    assert len(claim.citations) == 1
    assert claim.conflicting_evidence == []


def test_source_document():
    source = Source(
        source_type=SourceType.PAPER,
        title="Test Paper",
        content="This is the content of the paper.",
        doi="10.1234/test",
    )
    assert source.source_type == SourceType.PAPER
    assert source.content_hash is None  # Set by DocumentStore


def test_step_result():
    result = StepResult(
        step_id="step1",
        tool_name="web_search",
        status=StepStatus.SUCCESS,
        output={"data": [{"title": "Result", "url": "https://example.com", "snippet": "..."}]},
    )
    assert result.status == StepStatus.SUCCESS
    assert result.retries == 0
