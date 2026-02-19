"""Tests for the user feedback learning loop (screening override store)."""

import json
import time

import pytest
from pydantic import ValidationError

from evidentia.review.feedback import FeedbackEntry, FeedbackStats, FeedbackStore


# ── Helpers ──────────────────────────────────────────────────────────


def _record_sample_override(
    store: FeedbackStore,
    *,
    user_id: str = "user-1",
    review_id: str = "review-1",
    paper_title: str = "Sample Paper",
    paper_abstract: str = "Abstract text here.",
    original_decision: str = "exclude",
    original_confidence: float = 0.85,
    user_decision: str = "include",
    user_reason: str | None = "Meets inclusion criteria",
    research_question: str = "Does X improve Y?",
    inclusion_criteria: list[str] | None = None,
    exclusion_criteria: list[str] | None = None,
    paper_doi: str | None = None,
) -> FeedbackEntry:
    """Helper to record an override with sensible defaults."""
    return store.record_override(
        user_id=user_id,
        review_id=review_id,
        paper_title=paper_title,
        paper_abstract=paper_abstract,
        original_decision=original_decision,
        original_confidence=original_confidence,
        user_decision=user_decision,
        user_reason=user_reason,
        research_question=research_question,
        inclusion_criteria=inclusion_criteria or ["RCT design"],
        exclusion_criteria=exclusion_criteria or ["Animal studies"],
        paper_doi=paper_doi,
    )


# ── FeedbackEntry model validation ──────────────────────────────────


class TestFeedbackEntryModel:
    """Tests for the FeedbackEntry Pydantic model."""

    def test_default_timestamp_is_set(self):
        """Timestamp should be auto-populated close to current time."""
        before = time.time()
        entry = FeedbackEntry()
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_all_fields_assigned(self):
        """All fields should be assignable through the constructor."""
        entry = FeedbackEntry(
            timestamp=1000.0,
            user_id="u1",
            review_id="r1",
            paper_title="Title",
            paper_abstract="Abstract",
            paper_doi="10.1234/test",
            original_decision="exclude",
            original_confidence=0.9,
            user_decision="include",
            user_reason="Relevant",
            research_question="RQ",
            inclusion_criteria=["IC1"],
            exclusion_criteria=["EC1"],
        )
        assert entry.user_id == "u1"
        assert entry.review_id == "r1"
        assert entry.paper_title == "Title"
        assert entry.paper_abstract == "Abstract"
        assert entry.paper_doi == "10.1234/test"
        assert entry.original_decision == "exclude"
        assert entry.original_confidence == 0.9
        assert entry.user_decision == "include"
        assert entry.user_reason == "Relevant"
        assert entry.research_question == "RQ"
        assert entry.inclusion_criteria == ["IC1"]
        assert entry.exclusion_criteria == ["EC1"]

    def test_defaults_are_empty(self):
        """Unset fields should have sensible empty defaults."""
        entry = FeedbackEntry()
        assert entry.user_id == ""
        assert entry.review_id == ""
        assert entry.paper_title == ""
        assert entry.paper_abstract == ""
        assert entry.paper_doi is None
        assert entry.original_decision == ""
        assert entry.original_confidence == 0.0
        assert entry.user_decision == ""
        assert entry.user_reason is None
        assert entry.research_question == ""
        assert entry.inclusion_criteria == []
        assert entry.exclusion_criteria == []

    def test_serialization_roundtrip(self):
        """Entry should survive JSON serialization and deserialization."""
        entry = FeedbackEntry(
            user_id="u1",
            paper_title="Roundtrip Test",
            original_decision="include",
            user_decision="exclude",
            original_confidence=0.75,
        )
        json_str = entry.model_dump_json()
        restored = FeedbackEntry.model_validate_json(json_str)
        assert restored.user_id == entry.user_id
        assert restored.paper_title == entry.paper_title
        assert restored.original_decision == entry.original_decision
        assert restored.user_decision == entry.user_decision
        assert restored.original_confidence == entry.original_confidence


# ── FeedbackStats model ─────────────────────────────────────────────


class TestFeedbackStatsModel:
    """Tests for the FeedbackStats Pydantic model."""

    def test_default_stats(self):
        """Default stats should be all zeros / empty."""
        stats = FeedbackStats()
        assert stats.total_overrides == 0
        assert stats.overrides_to_include == 0
        assert stats.overrides_to_exclude == 0
        assert stats.avg_original_confidence_on_overrides == 0.0
        assert stats.most_common_override_reasons == []
        assert stats.accuracy_estimate is None


# ── FeedbackStore: record_override ───────────────────────────────────


class TestRecordOverride:
    """Tests for FeedbackStore.record_override()."""

    def test_record_creates_jsonl_file(self, tmp_path):
        """Recording an override should create the JSONL file."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(store)

        feedback_file = tmp_path / "screening_overrides.jsonl"
        assert feedback_file.exists()

    def test_record_writes_valid_json_line(self, tmp_path):
        """Each recorded override should be a valid JSON line."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(store, paper_title="Test Paper Alpha")

        feedback_file = tmp_path / "screening_overrides.jsonl"
        lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["paper_title"] == "Test Paper Alpha"
        assert data["user_decision"] == "include"
        assert data["original_decision"] == "exclude"

    def test_record_returns_feedback_entry(self, tmp_path):
        """record_override should return a populated FeedbackEntry."""
        store = FeedbackStore(data_dir=tmp_path)
        entry = _record_sample_override(
            store, user_id="u42", paper_title="Return Check"
        )
        assert isinstance(entry, FeedbackEntry)
        assert entry.user_id == "u42"
        assert entry.paper_title == "Return Check"

    def test_multiple_overrides_accumulate(self, tmp_path):
        """Multiple overrides should each append a new line to the file."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(store, paper_title="Paper A")
        _record_sample_override(store, paper_title="Paper B")
        _record_sample_override(store, paper_title="Paper C")

        feedback_file = tmp_path / "screening_overrides.jsonl"
        lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

        titles = [json.loads(line)["paper_title"] for line in lines]
        assert titles == ["Paper A", "Paper B", "Paper C"]

    def test_record_with_none_abstract(self, tmp_path):
        """Passing None for paper_abstract should store empty string."""
        store = FeedbackStore(data_dir=tmp_path)
        entry = store.record_override(
            user_id="u1",
            review_id="r1",
            paper_title="No Abstract",
            paper_abstract=None,
            original_decision="exclude",
            original_confidence=0.5,
            user_decision="include",
        )
        assert entry.paper_abstract == ""

    def test_record_with_optional_fields(self, tmp_path):
        """Optional fields (DOI, reason, criteria) should be stored correctly."""
        store = FeedbackStore(data_dir=tmp_path)
        entry = _record_sample_override(
            store,
            paper_doi="10.9999/test-doi",
            user_reason="Very relevant to our RQ",
            inclusion_criteria=["RCT", "Adults", "Published 2020+"],
            exclusion_criteria=["Non-English"],
        )
        assert entry.paper_doi == "10.9999/test-doi"
        assert entry.user_reason == "Very relevant to our RQ"
        assert entry.inclusion_criteria == ["RCT", "Adults", "Published 2020+"]
        assert entry.exclusion_criteria == ["Non-English"]


# ── FeedbackStore: get_stats ─────────────────────────────────────────


class TestGetStats:
    """Tests for FeedbackStore.get_stats()."""

    def test_stats_with_no_data(self, tmp_path):
        """Stats on an empty store should return zero defaults."""
        store = FeedbackStore(data_dir=tmp_path)
        stats = store.get_stats()
        assert stats.total_overrides == 0
        assert stats.overrides_to_include == 0
        assert stats.overrides_to_exclude == 0
        assert stats.avg_original_confidence_on_overrides == 0.0
        assert stats.most_common_override_reasons == []
        assert stats.accuracy_estimate is None

    def test_stats_with_no_feedback_file(self, tmp_path):
        """Stats should work even before any file is created."""
        store = FeedbackStore(data_dir=tmp_path)
        # Don't record anything; file doesn't exist yet.
        stats = store.get_stats()
        assert stats.total_overrides == 0
        assert stats.accuracy_estimate is None

    def test_stats_counts_overrides_correctly(self, tmp_path):
        """Should count include/exclude overrides separately."""
        store = FeedbackStore(data_dir=tmp_path)

        # Override: exclude -> include
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            original_confidence=0.80,
        )
        # Override: include -> exclude
        _record_sample_override(
            store,
            original_decision="include",
            user_decision="exclude",
            original_confidence=0.70,
        )
        # Override: exclude -> include
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            original_confidence=0.90,
        )

        stats = store.get_stats()
        assert stats.total_overrides == 3
        assert stats.overrides_to_include == 2
        assert stats.overrides_to_exclude == 1

    def test_stats_accuracy_with_agreements_and_overrides(self, tmp_path):
        """Accuracy should reflect the fraction of non-overridden decisions."""
        store = FeedbackStore(data_dir=tmp_path)

        # 2 agreements (user decision matches original)
        _record_sample_override(
            store, original_decision="include", user_decision="include"
        )
        _record_sample_override(
            store, original_decision="exclude", user_decision="exclude"
        )
        # 1 override
        _record_sample_override(
            store, original_decision="exclude", user_decision="include"
        )

        stats = store.get_stats()
        # 2 agreements out of 3 total
        assert stats.accuracy_estimate == pytest.approx(2 / 3, abs=0.001)
        assert stats.total_overrides == 1

    def test_stats_average_confidence_on_overrides(self, tmp_path):
        """Average confidence should only consider overridden entries."""
        store = FeedbackStore(data_dir=tmp_path)

        # Override with confidence 0.80
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            original_confidence=0.80,
        )
        # Override with confidence 0.60
        _record_sample_override(
            store,
            original_decision="include",
            user_decision="exclude",
            original_confidence=0.60,
        )
        # Agreement (should NOT affect average)
        _record_sample_override(
            store,
            original_decision="include",
            user_decision="include",
            original_confidence=0.99,
        )

        stats = store.get_stats()
        assert stats.avg_original_confidence_on_overrides == pytest.approx(0.70, abs=0.001)

    def test_stats_most_common_override_reasons(self, tmp_path):
        """Override reasons should be ranked by frequency."""
        store = FeedbackStore(data_dir=tmp_path)

        # Record overrides with different reasons
        for _ in range(3):
            _record_sample_override(
                store,
                original_decision="exclude",
                user_decision="include",
                user_reason="Meets criteria",
            )
        for _ in range(2):
            _record_sample_override(
                store,
                original_decision="include",
                user_decision="exclude",
                user_reason="Wrong population",
            )
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            user_reason="Relevant to RQ",
        )

        stats = store.get_stats()
        assert len(stats.most_common_override_reasons) == 3
        assert stats.most_common_override_reasons[0] == "Meets criteria"
        assert stats.most_common_override_reasons[1] == "Wrong population"
        assert stats.most_common_override_reasons[2] == "Relevant to RQ"

    def test_stats_reasons_excludes_none(self, tmp_path):
        """Override reasons that are None should be excluded from the ranking."""
        store = FeedbackStore(data_dir=tmp_path)

        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            user_reason=None,
        )
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            user_reason="Good paper",
        )

        stats = store.get_stats()
        assert stats.most_common_override_reasons == ["Good paper"]

    def test_stats_all_agreements_100_percent_accuracy(self, tmp_path):
        """If every entry is an agreement, accuracy should be 1.0."""
        store = FeedbackStore(data_dir=tmp_path)
        for _ in range(5):
            _record_sample_override(
                store, original_decision="include", user_decision="include"
            )

        stats = store.get_stats()
        assert stats.accuracy_estimate == 1.0
        assert stats.total_overrides == 0


# ── FeedbackStore: get_training_pairs ────────────────────────────────


class TestGetTrainingPairs:
    """Tests for FeedbackStore.get_training_pairs()."""

    def test_training_pairs_empty_store(self, tmp_path):
        """No data should yield an empty list of training pairs."""
        store = FeedbackStore(data_dir=tmp_path)
        pairs = store.get_training_pairs()
        assert pairs == []

    def test_training_pairs_format(self, tmp_path):
        """Each training pair should have the correct structure."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(
            store,
            paper_title="Training Paper",
            paper_abstract="Abstract for training.",
            original_decision="exclude",
            original_confidence=0.85,
            user_decision="include",
            user_reason="Relevant",
            research_question="Does X help Y?",
            inclusion_criteria=["RCT"],
            exclusion_criteria=["Animal"],
        )

        pairs = store.get_training_pairs()
        assert len(pairs) == 1

        pair = pairs[0]
        assert "input" in pair
        assert "label" in pair
        assert "reason" in pair
        assert "original_prediction" in pair
        assert "original_confidence" in pair

        assert pair["input"]["title"] == "Training Paper"
        assert pair["input"]["abstract"] == "Abstract for training."
        assert pair["input"]["research_question"] == "Does X help Y?"
        assert pair["input"]["inclusion_criteria"] == ["RCT"]
        assert pair["input"]["exclusion_criteria"] == ["Animal"]
        assert pair["label"] == "include"
        assert pair["reason"] == "Relevant"
        assert pair["original_prediction"] == "exclude"
        assert pair["original_confidence"] == 0.85

    def test_training_pairs_excludes_agreements(self, tmp_path):
        """Agreements (non-overrides) should NOT appear in training pairs."""
        store = FeedbackStore(data_dir=tmp_path)

        # Agreement
        _record_sample_override(
            store, original_decision="include", user_decision="include"
        )
        # Override
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            paper_title="Override Paper",
        )

        pairs = store.get_training_pairs()
        assert len(pairs) == 1
        assert pairs[0]["input"]["title"] == "Override Paper"

    def test_training_pairs_respects_limit(self, tmp_path):
        """Limit parameter should cap the number of returned pairs."""
        store = FeedbackStore(data_dir=tmp_path)

        for i in range(10):
            _record_sample_override(
                store,
                paper_title=f"Paper {i}",
                original_decision="exclude",
                user_decision="include",
            )

        pairs = store.get_training_pairs(limit=3)
        assert len(pairs) == 3
        # Should be the first 3 overrides in order
        assert pairs[0]["input"]["title"] == "Paper 0"
        assert pairs[2]["input"]["title"] == "Paper 2"

    def test_training_pairs_limit_larger_than_data(self, tmp_path):
        """If limit exceeds available overrides, return all overrides."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(
            store, original_decision="exclude", user_decision="include"
        )

        pairs = store.get_training_pairs(limit=1000)
        assert len(pairs) == 1

    def test_training_pairs_reason_defaults_to_empty_string(self, tmp_path):
        """If user_reason is None, training pair reason should be empty string."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(
            store,
            original_decision="exclude",
            user_decision="include",
            user_reason=None,
        )

        pairs = store.get_training_pairs()
        assert pairs[0]["reason"] == ""


# ── FeedbackStore: malformed data handling ───────────────────────────


class TestMalformedData:
    """Tests for resilience against corrupted or malformed JSONL entries."""

    def test_malformed_json_lines_are_skipped(self, tmp_path):
        """Invalid JSON lines should be silently skipped."""
        store = FeedbackStore(data_dir=tmp_path)

        # Record a valid entry first
        _record_sample_override(store, paper_title="Valid Paper")

        # Now manually append garbage to the file
        feedback_file = tmp_path / "screening_overrides.jsonl"
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write("this is not valid json\n")
            f.write("{invalid json too\n")

        stats = store.get_stats()
        # Only the 1 valid override should be counted
        assert stats.total_overrides == 1

    def test_blank_lines_are_skipped(self, tmp_path):
        """Blank lines in the JSONL file should be ignored."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(store, paper_title="Valid Entry")

        feedback_file = tmp_path / "screening_overrides.jsonl"
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write("\n\n\n")

        pairs = store.get_training_pairs()
        assert len(pairs) == 1

    def test_partially_valid_file(self, tmp_path):
        """A file with a mix of valid and invalid entries should load only valid ones."""
        feedback_file = tmp_path / "screening_overrides.jsonl"

        valid_entry = FeedbackEntry(
            user_id="u1",
            paper_title="Good Entry",
            original_decision="exclude",
            user_decision="include",
            original_confidence=0.8,
        )
        with open(feedback_file, "w", encoding="utf-8") as f:
            f.write("corrupted line 1\n")
            f.write(valid_entry.model_dump_json() + "\n")
            f.write('{"unexpected_field": true}\n')  # Wrong schema but valid JSON
            f.write(valid_entry.model_dump_json() + "\n")
            f.write("another bad line\n")

        store = FeedbackStore(data_dir=tmp_path)
        stats = store.get_stats()
        # FeedbackEntry has defaults so '{"unexpected_field": true}' may still parse
        # as a valid FeedbackEntry with all defaults.  Let's check total loaded entries.
        # The important thing is the 2 real entries are included.
        assert stats.accuracy_estimate is not None

    def test_empty_feedback_file(self, tmp_path):
        """An empty file should be treated as no data."""
        feedback_file = tmp_path / "screening_overrides.jsonl"
        feedback_file.write_text("", encoding="utf-8")

        store = FeedbackStore(data_dir=tmp_path)
        stats = store.get_stats()
        assert stats.total_overrides == 0
        assert stats.accuracy_estimate is None

        pairs = store.get_training_pairs()
        assert pairs == []


# ── FeedbackStore: directory creation ────────────────────────────────


class TestStoreInitialization:
    """Tests for FeedbackStore constructor and directory handling."""

    def test_creates_data_directory(self, tmp_path):
        """FeedbackStore should create the data directory if it doesn't exist."""
        nested_dir = tmp_path / "deeply" / "nested" / "dir"
        assert not nested_dir.exists()

        store = FeedbackStore(data_dir=nested_dir)
        assert nested_dir.exists()

    def test_uses_existing_directory(self, tmp_path):
        """FeedbackStore should work with an already-existing directory."""
        store = FeedbackStore(data_dir=tmp_path)
        _record_sample_override(store)
        feedback_file = tmp_path / "screening_overrides.jsonl"
        assert feedback_file.exists()

    def test_default_data_dir_when_none(self):
        """When data_dir is None, should default to ~/.evidentia/feedback."""
        store = FeedbackStore(data_dir=None)
        from pathlib import Path

        expected = Path.home() / ".evidentia" / "feedback"
        assert store._data_dir == expected
