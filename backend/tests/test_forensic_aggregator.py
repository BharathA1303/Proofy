"""
backend/tests/test_forensic_aggregator.py

Unit tests for Module 3 conservative signal aggregation.

These pin down the acceptance criteria that:
  - one weak signal never escalates the result
  - multiple independent indicators (or one strong one) DO escalate it
"""
from app.services.forensics.aggregator import SignalVote, aggregate_forensic_signals


class TestAggregation:
    def test_no_signals_is_no_significant_anomaly(self):
        overall, _ = aggregate_forensic_signals([])
        assert overall == "no_significant_anomaly"

    def test_all_normal_signals_is_no_significant_anomaly(self):
        votes = [
            SignalVote(type="ela", status="normal", severity="low"),
            SignalVote(type="photo_boundary", status="normal", severity="low"),
            SignalVote(type="compression", status="normal", severity="low"),
        ]
        overall, _ = aggregate_forensic_signals(votes)
        assert overall == "no_significant_anomaly"

    def test_one_weak_signal_does_not_escalate(self):
        votes = [
            SignalVote(type="ela", status="suspicious", severity="medium"),
            SignalVote(type="photo_boundary", status="normal", severity="low"),
        ]
        overall, _ = aggregate_forensic_signals(votes)
        assert overall == "no_significant_anomaly"

    def test_two_weak_signals_are_suspicious(self):
        votes = [
            SignalVote(type="ela", status="suspicious", severity="medium"),
            SignalVote(type="photo_boundary", status="suspicious", severity="medium"),
        ]
        overall, _ = aggregate_forensic_signals(votes)
        assert overall == "suspicious"

    def test_one_strong_signal_is_suspicious(self):
        votes = [
            SignalVote(type="ela", status="suspicious", severity="high"),
        ]
        overall, _ = aggregate_forensic_signals(votes)
        assert overall == "suspicious"

    def test_two_strong_signals_are_high_forensic_concern(self):
        votes = [
            SignalVote(type="ela", status="suspicious", severity="high"),
            SignalVote(type="photo_boundary", status="suspicious", severity="high"),
        ]
        overall, _ = aggregate_forensic_signals(votes)
        assert overall == "high_forensic_concern"

    def test_explanation_is_never_a_fraud_declaration(self):
        votes = [
            SignalVote(type="ela", status="suspicious", severity="high"),
            SignalVote(type="photo_boundary", status="suspicious", severity="high"),
        ]
        _, explanation = aggregate_forensic_signals(votes)
        forbidden = ["forged", "fake", "definitely"]
        assert not any(word in explanation.lower() for word in forbidden)
