from __future__ import annotations

from src.bot.scheduler import _should_commit_delivery_state


def test_normal_digest_dedup_keeps_material_change_pending() -> None:
    assert (
        _should_commit_delivery_state(
            sent=False,
            delivery_mode="digest",
            priority_bypass=False,
        )
        is False
    )


def test_sent_digest_advances_delivery_baseline() -> None:
    assert (
        _should_commit_delivery_state(
            sent=True,
            delivery_mode="digest",
            priority_bypass=False,
        )
        is True
    )


def test_high_priority_digest_dedup_advances_delivery_baseline() -> None:
    assert (
        _should_commit_delivery_state(
            sent=False,
            delivery_mode="digest",
            priority_bypass=True,
        )
        is True
    )


def test_immediate_transition_dedup_advances_delivery_baseline() -> None:
    assert (
        _should_commit_delivery_state(
            sent=False,
            delivery_mode="immediate",
            priority_bypass=False,
        )
        is True
    )
