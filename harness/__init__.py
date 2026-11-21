"""Process harness: policy/env/scorer subprocesses, JSONL protocol, trajectory, sandbox, and replay (Phase 9, Zone 2)."""

from __future__ import annotations

from typing import Any

from harness.env_process import EnvSubprocess
from harness.isolated_runner import (
    EpisodeRunResult,
    run_inprocess_judge_policy,
    run_isolated_public_policy,
)
from harness.policy_process import PolicySubprocess
from harness.protocol import (
    DEFAULT_FORBIDDEN_TOKENS,
    MAX_JSONL_LINE_BYTES,
    LeakageViolationError,
    ProtocolError,
    assert_policy_outbound_clean,
    format_policy_reset_frame,
    format_policy_response_frame,
    format_policy_terminate_frame,
    read_bounded_line,
    validate_tool_request_line,
    write_jsonl_line,
)
from harness.runner import (
    ClosedEvalRunResult,
    ProcessLifecycleProof,
    run_closed_eval_batch,
    run_closed_eval_episode,
)
from harness.sandbox import (
    ALLOWLISTED_PUBLIC_FILENAMES,
    IsolatedPolicyWorkspace,
    SecurityProfile,
    StagedPublicWorkspace,
    build_sanitized_env,
    detect_security_profile,
    make_posix_preexec,
)
from harness.scorer_process import (
    ScorerPrematureStartError,
    ScorerProcessResult,
    run_scorer_subprocess,
    seal_receipt_batch_subprocess,
    verify_receipt_subprocess,
)
from harness.trajectory import (
    RecordedTrajectoryEntry,
    TrajectoryRecorder,
    compute_initial_chain_hash,
    compute_next_chain_hash,
    load_recorded_trajectory_jsonl,
)

_LAZY_REPLAY_EXPORTS = frozenset(
    {
        "ReplayEpisodeResult",
        "replay_episode",
        "run_replay_verification_suite",
    }
)


def __getattr__(name: str) -> Any:
    if name in _LAZY_REPLAY_EXPORTS:
        import harness.replay as _replay

        return getattr(_replay, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ALLOWLISTED_PUBLIC_FILENAMES",
    "DEFAULT_FORBIDDEN_TOKENS",
    "MAX_JSONL_LINE_BYTES",
    "ClosedEvalRunResult",
    "EnvSubprocess",
    "EpisodeRunResult",
    "IsolatedPolicyWorkspace",
    "LeakageViolationError",
    "PolicySubprocess",
    "ProcessLifecycleProof",
    "ProtocolError",
    "RecordedTrajectoryEntry",
    "ReplayEpisodeResult",
    "ScorerPrematureStartError",
    "ScorerProcessResult",
    "SecurityProfile",
    "StagedPublicWorkspace",
    "TrajectoryRecorder",
    "assert_policy_outbound_clean",
    "build_sanitized_env",
    "compute_initial_chain_hash",
    "compute_next_chain_hash",
    "detect_security_profile",
    "format_policy_reset_frame",
    "format_policy_response_frame",
    "format_policy_terminate_frame",
    "load_recorded_trajectory_jsonl",
    "make_posix_preexec",
    "read_bounded_line",
    "replay_episode",
    "run_closed_eval_batch",
    "run_closed_eval_episode",
    "run_inprocess_judge_policy",
    "run_isolated_public_policy",
    "run_replay_verification_suite",
    "run_scorer_subprocess",
    "seal_receipt_batch_subprocess",
    "validate_tool_request_line",
    "verify_receipt_subprocess",
    "write_jsonl_line",
]
