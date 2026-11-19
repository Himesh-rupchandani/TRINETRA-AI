"""Analysis must not queue work on an undersized or pressured backend."""
import pytest

from app.core import vision
from app.services import video_analysis_service as vas


def test_analysis_rejects_memory_budget_before_touching_database(monkeypatch):
    monkeypatch.setattr(vision, "vision_available", lambda: True)
    monkeypatch.setattr(vas, "inference_budget", lambda: {
        "allowed": False,
        "reason": "AI paused: this container has 512 MB RAM; use a larger ML backend.",
    })

    # No rows are changed and no workers started if admission fails.
    class UntouchedDatabase:
        def query(self, *_args):
            pytest.fail("database must not be queried when memory is insufficient")

    with pytest.raises(vas.AnalysisError, match="512 MB RAM"):
        vas.start_analysis(UntouchedDatabase())
