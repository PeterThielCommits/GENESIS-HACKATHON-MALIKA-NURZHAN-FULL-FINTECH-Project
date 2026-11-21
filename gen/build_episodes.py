"""Episode assembly: clean twin -> distractors -> operators -> diff -> truth (Phase 4).

Pipeline implemented here (Mастер TЗ 10.2 stages G1..G16, with the verifier
cross-check G13/G14 delegated to Phase 8 and represented by a pluggable hook):

  G1  validated config            G9  operators applied to a copy
  G2-G5 clean twin                G10 deterministic table ordering
  G6  documents + JEs             G11 structural diff
  G7  invariants (clean)          G12 candidate truth from diff + declaration
  G8  multilingual text           G13/G14 verifier cross-check (hook, Phase 8)
                                  G15 shortcut/ambiguity gates
                                  G16 commitment + manifest

Nothing here writes private data into the public package: public files are exactly
``Book.public_files()``; truth, provenance and reject logs go to ``sealed/``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from contracts.canonical import digest_of, sha256_hex
from contracts.errors import ConfigError, OperatorError, RejectError
from gen.clean import GENERATOR_VERSION, CleanBuild, build_clean_book
from gen.config import GeneratorConfig
from gen.distractors import DISTRACTOR_IDS, Distractor, build_distractors
from gen.errors.base import MutationOperator, OperatorApplication
from gen.errors.registry import factory_for, operator_ids
from gen.errors.signatures import SignatureDecision, verify_signature
from gen.reject import RejectLog, Rejected, assert_distinct_affected_ids, reject, sample
from gen.truth_build import CandidateFinding, TruthBuild, build_candidate_truth
from gen.truthdiff import TwinDiff, structural_diff
from gen.twins import Book, TwinPair
from invariants.checks_clean import check_all
from invariants.model import Violation

CONTRACT_VERSION = "1.0.0"
MANIFEST_VERSION = "1.0.0"
CANARY_SCAN_VERSION = "canary-scan-1.0.0"

# Selection is driven by ``gen.errors.registry`` so an operator cannot be built
# without also being registered (and therefore validated against the catalogue).
OPERATORS: dict[str, type[MutationOperator]] = {
    operator_id: factory_for(operator_id) for operator_id in operator_ids()
}

VerifierHook = Callable[[Book, Mapping[str, Any]], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class EpisodePackage:
    """Complete in-memory episode: public text, sealed truth, provenance, report."""

    episode_id: str
    difficulty: str
    mode: str
    public_files: Mapping[str, str]
    manifest: Mapping[str, Any]
    truth: Mapping[str, Any]
    provenance: Mapping[str, Any]
    verifier_report: Mapping[str, Any]
    reject_stats: Mapping[str, Any]
    twin: TwinPair
    findings: tuple[CandidateFinding, ...]
    distractors: tuple[Distractor, ...]
    diff: TwinDiff
    signature_decisions: tuple[SignatureDecision, ...]

    @property
    def public_digest(self) -> str:
        return str(self.manifest["public_digest"])

    def sealed_files(self) -> dict[str, str]:
        """Sealed payloads, serialised canonically (never written under public/)."""
        from contracts.canonical import canonical_json

        return {
            "truth.json": canonical_json(self.truth) + "\n",
            "provenance.json": canonical_json(self.provenance) + "\n",
            "verifier_crosscheck.json": canonical_json(self.verifier_report) + "\n",
            "reject_log.json": canonical_json(self.reject_stats) + "\n",
        }


def build_episode(
    *,
    master_seed: str,
    config: GeneratorConfig,
    difficulty: str = "L1",
    anomaly_count: int | None = None,
    episode_id: str | None = None,
    verifier_hook: VerifierHook | None = None,
    created_at: str | None = None,
) -> EpisodePackage:
    """Build one deterministic episode; raises ``RejectBudgetExhausted`` if unpublishable."""
    config.validate()
    profile = config.profile(difficulty)
    mutation_cfg = config.mutation_raw["mutation"]
    requested = int(profile["anomaly_count"]) if anomaly_count is None else anomaly_count
    if requested < 0:
        raise ConfigError("anomaly_count must be >= 0", anomaly_count=requested)
    if requested > int(mutation_cfg["max_anomalies_per_episode"]):
        raise ConfigError(
            "anomaly_count exceeds configured maximum",
            anomaly_count=requested,
            maximum=mutation_cfg["max_anomalies_per_episode"],
        )

    log = RejectLog()
    limit = int(mutation_cfg["reject_attempt_limit"])

    if requested == 0:
        return _build_clean_episode(
            master_seed=master_seed,
            config=config,
            difficulty=difficulty,
            episode_id=episode_id,
            created_at=created_at,
        )

    def attempt(index: int) -> EpisodePackage:
        return _attempt_episode(
            master_seed=master_seed,
            config=config,
            difficulty=difficulty,
            requested=requested,
            attempt_index=index,
            episode_id=episode_id,
            verifier_hook=verifier_hook,
            created_at=created_at,
            log=log,
        )

    return sample(attempt=attempt, limit=limit, log=log)


# --------------------------------------------------------------------- internal
def _mark_acceptance(log: RejectLog) -> None:
    """A published episode is accepted regardless of how many retries it took."""
    log.accepted = True


def _clean_or_reject(
    master_seed: str, config: GeneratorConfig, difficulty: str
) -> CleanBuild:
    build = build_clean_book(master_seed=master_seed, config=config, difficulty=difficulty)
    if not build.clean:
        reject(
            "CLEAN_TWIN_INVARIANT_VIOLATION",
            invariants=sorted({violation.invariant_id for violation in build.violations}),
        )
    return build


def _attempt_episode(
    *,
    master_seed: str,
    config: GeneratorConfig,
    difficulty: str,
    requested: int,
    attempt_index: int,
    episode_id: str | None,
    verifier_hook: VerifierHook | None,
    created_at: str | None,
    log: RejectLog,
) -> EpisodePackage:
    clean_build = _clean_or_reject(master_seed, config, difficulty)
    clean_book = clean_build.book
    clean_digest = clean_book.public_digest()

    mutation_cfg = config.mutation_raw["mutation"]
    operator_order: list[str] = [
        name for name in mutation_cfg["operator_order"] if name in OPERATORS
    ]
    if not operator_order:
        reject(
            "NO_CANDIDATE_PARAMS", detail="no operators configured")

    # Deterministic operator selection: the *seed* decides the starting family (so a
    # seed set covers every family), and retries advance through the configured
    # order instead of repeating the same rejection.
    seed_offset = int(sha256_hex(master_seed)[:8], 16) % len(operator_order)
    selected: list[str] = [
        operator_order[(seed_offset + attempt_index + offset) % len(operator_order)]
        for offset in range(requested)
    ]

    mutated = clean_book
    states: list[Book] = [clean_book]  # states[i] = book before operator i
    applications: list[OperatorApplication] = []
    findings: list[CandidateFinding] = []
    decisions: list[SignatureDecision] = []
    diffs: list[TwinDiff] = []

    from gen.core.rng import RngService

    rng_service = RngService(master_seed)

    for index, operator_id in enumerate(selected):
        # A family can legitimately have no valid target on a given clean twin (an
        # L1 book may carry no credit note, for example). Fall back to another
        # configured family that *does* have candidates before rejecting the attempt.
        operator, operator_cfg, candidates = _resolve_operator(mutated, config, selected, index)
        if candidates is None:
            reject(
                "NO_CANDIDATE_PARAMS",
                operator=operator_id,
                index=index,
                configured=list(operator_order),
            )
        operator_id = operator.spec.operator_id
        # Deterministic, seed-derived choice over the candidate list. Selection is
        # *not* positional: taking ``candidates[k]`` for a fixed ``k`` would let the
        # first configured subtype dominate every episode once the list is ordered by
        # weight. The RNG stream is namespaced per attempt, so a retry explores a
        # different target instead of repeating the same rejection.
        stream = rng_service.stream(
            f"mutation/{operator_id}/{index}/{attempt_index}"
        )
        pool = candidates
        table = operator.selection_table(candidates, operator_cfg)
        if table is not None:
            field, weights = table
            chosen = stream.choices_weighted(dict(weights))
            narrowed = [item for item in candidates if str(item.get(field)) == chosen]
            if narrowed:
                pool = narrowed
        candidate = dict(stream.choice(pool))
        try:
            mutated, application = operator.apply(mutated, candidate, stream)
        except OperatorError as exc:
            reject(
            "OPERATOR_APPLICATION_FAILED",
                operator=operator_id,
                index=index,
                reason=exc.code,
            )
            raise AssertionError("unreachable")  # pragma: no cover

        # Causal attribution (11.7): the delta is measured between the state right
        # before this operator and the state right after it. Adding a second operator
        # therefore cannot silently re-attribute the first one's changes.
        diff = structural_diff(states[index], mutated)
        violations = check_all(mutated)
        subtype = candidate.get("subtype")
        decision = verify_signature(
            operator.spec.anomaly_type, violations, subtype=subtype
        )
        decisions.append(decision)
        if not decision.accepted:
            reject(
            "SIGNATURE_MISMATCH",
                operator=operator_id,
                index=index,
                observed=list(decision.observed),
            )
        try:
            truth_build = build_candidate_truth(
                clean=clean_book,
                mutated=mutated,
                diff=diff,
                violations=violations,
                application=application,
                subtype=subtype,
            )
        except RejectError as exc:
            reject(
            "UNREACHABLE_EVIDENCE", operator=operator_id, index=index, reason=exc.code)
            raise AssertionError("unreachable")  # pragma: no cover
        except Exception as exc:  # ContractError: diff-backed assertion failed
            reject(
            "DIFF_INCONSISTENT",
                operator=operator_id,
                index=index,
                reason=type(exc).__name__,
            )
            raise AssertionError("unreachable")  # pragma: no cover

        applications.append(application)
        findings.extend(truth_build.findings)
        diffs.append(diff)
        states.append(mutated)

    if states[0].public_digest() != clean_digest:
        reject("CLEAN_TWIN_MUTATED")

    truth_findings = [finding.describe() for finding in findings]
    try:
        assert_distinct_affected_ids(truth_findings)
    except Rejected as exc:
        reject(exc.reason, detail="findings share affected ids")

    # Distractors: clean look-alikes observed on the clean twin (11.6).
    max_distractors = int(config.mutation_raw["distractors"]["max_active_per_episode"])
    requested_ids: list[str] = []
    seen_types: set[str] = set()
    for finding in findings:
        if finding.anomaly_type in seen_types:
            continue
        seen_types.add(finding.anomaly_type)
        requested_ids.extend(DISTRACTOR_IDS.get(finding.anomaly_type, ())[:2])
    distractors = build_distractors(
        clean_book, requested=requested_ids, max_active=max_distractors
    )

    total_diff = structural_diff(clean_book, mutated)
    truth_build = TruthBuild(
        findings=tuple(findings),
        diff=total_diff,
        evidence_index={},
        notes=(),
    )

    _mark_acceptance(log)
    return _assemble(
        clean_build=clean_build,
        mutated=mutated,
        config=config,
        difficulty=difficulty,
        episode_id=episode_id or _episode_id(master_seed, config, difficulty),
        mode="ANOMALOUS",
        truth_build=truth_build,
        distractors=distractors,
        applications=applications,
        decisions=decisions,
        log=log,
        verifier_hook=verifier_hook,
        created_at=created_at,
        attempt_index=attempt_index,
    )


def _build_clean_episode(
    *,
    master_seed: str,
    config: GeneratorConfig,
    difficulty: str,
    episode_id: str | None,
    created_at: str | None,
) -> EpisodePackage:
    build = _clean_or_reject(master_seed, config, difficulty)
    log = RejectLog(accepted=True)
    diff = structural_diff(build.book, build.book)
    truth_build = TruthBuild(findings=(), diff=diff, evidence_index={}, notes=("clean episode",))
    return _assemble(
        clean_build=build,
        mutated=build.book,
        config=config,
        difficulty=difficulty,
        episode_id=episode_id or _episode_id(master_seed, config, difficulty),
        mode="CLEAN",
        truth_build=truth_build,
        distractors=(),
        applications=[],
        decisions=[],
        log=log,
        verifier_hook=None,
        created_at=created_at,
        attempt_index=0,
    )


def _assemble(
    *,
    clean_build: CleanBuild,
    mutated: Book,
    config: GeneratorConfig,
    difficulty: str,
    episode_id: str,
    mode: str,
    truth_build: TruthBuild,
    distractors: Sequence[Distractor],
    applications: Sequence[OperatorApplication],
    decisions: Sequence[SignatureDecision],
    log: RejectLog,
    verifier_hook: VerifierHook | None,
    created_at: str | None,
    attempt_index: int,
) -> EpisodePackage:
    clean_book = clean_build.book
    public_files = mutated.public_files()
    file_hashes = mutated.file_hashes()
    truth = truth_build.to_truth_document(episode_id=episode_id, mode=mode)
    truth["distractors"] = [distractor.to_truth_entry() for distractor in distractors]

    truth_digest = digest_of(truth)
    salt = _commitment_salt(config.config_hash, episode_id)
    commitment = sha256_hex(f"{salt}{truth_digest}".encode("utf-8"))

    canaries = _canaries(config.config_hash, episode_id, clean_build.master_seed_digest)
    scans = _scan_public(public_files, canaries, config)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "episode_id": episode_id,
        "difficulty": difficulty,
        "contract_version": CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "config_hash": config.config_hash,
        "schema_versions": _schema_versions(),
        "public_files": [
            {
                "name": name,
                "sha256": file_hashes[name],
                "bytes": len(public_files[name].encode("utf-8")),
                "rows": _row_count(name, mutated),
            }
            for name in sorted(public_files)
        ],
        "public_digest": mutated.public_digest(),
        "commitment": {
            "algorithm": "sha256(salt||truth_digest)",
            "commitment_hex": commitment,
        },
        "table_counts": mutated.row_counts(),
        "timezone": mutated.company["timezone"],
        "functional_currency": mutated.company["functional_currency"],
        "created_at_utc": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "canary_scan": {
            "scan_version": CANARY_SCAN_VERSION,
            "public_hits": 0,
        },
    }

    provenance = {
        "provenance_version": "1.0.0",
        "episode_id": episode_id,
        "master_seed_digest": clean_build.master_seed_digest,
        "base_config_hash": config.config_hash,
        "clean_public_digest": clean_book.public_digest(),
        "mutated_public_digest": mutated.public_digest(),
        "operator_applications": [
            {**application.to_provenance(), "index": index}
            for index, application in enumerate(applications)
        ],
        "canaries": canaries,
        "reject_stats": log.to_stats(),
        "distractors": [
            {
                "distractor_id": distractor.distractor_id,
                "distractor_of": distractor.distractor_of,
                "distinguishing_fact": distractor.distinguishing_fact,
                "public_evidence_ids": list(distractor.public_evidence_ids),
            }
            for distractor in distractors
        ],
        "diff_summary": truth_build.diff.summary(),
        "signature_decisions": [decision.to_dict() for decision in decisions],
        "attempt_index": attempt_index,
    }

    verifier_report: dict[str, Any]
    if verifier_hook is None:
        verifier_report = {
            "status": "DEFERRED_TO_PHASE_8",
            "checked_invariants": [],
            "findings": [],
            "notes": [
                "Independent verifier is delivered in Phase 8; the generator-side "
                "invariant suite and error-matrix comparison already validated this episode.",
            ],
        }
    else:
        external = list(verifier_hook(mutated, truth))
        verifier_report = {
            "status": "CROSS_CHECKED",
            "findings": external,
            "notes": ["Verifier cross-check executed via hook."],
        }

    return EpisodePackage(
        episode_id=episode_id,
        difficulty=difficulty,
        mode=mode,
        public_files=public_files,
        manifest=manifest,
        truth=truth,
        provenance=provenance,
        verifier_report=verifier_report,
        reject_stats=log.to_stats(),
        twin=TwinPair(clean=clean_book, mutated=mutated),
        findings=tuple(truth_build.findings),
        distractors=tuple(distractors),
        diff=truth_build.diff,
        signature_decisions=tuple(decisions),
    )


# --------------------------------------------------------------------- helpers
def _resolve_operator(
    book: Book,
    config: GeneratorConfig,
    selected: Sequence[str],
    index: int,
) -> tuple[MutationOperator, Mapping[str, Any], list[dict[str, Any]] | None]:
    """Pick an operator with usable candidates, preferring the scheduled one."""
    order = list(selected[index:]) + list(selected[:index])
    for operator_id in dict.fromkeys(order):
        operator = OPERATORS[operator_id]()
        operator_cfg = _operator_config(config, operator_id)
        candidates = operator.candidate_params(book, operator_cfg)
        if candidates:
            return operator, operator_cfg, candidates
    for operator_id in OPERATORS:
        operator = OPERATORS[operator_id]()
        operator_cfg = _operator_config(config, operator_id)
        candidates = operator.candidate_params(book, operator_cfg)
        if candidates:
            return operator, operator_cfg, candidates
    return OPERATORS[order[0]](), _operator_config(config, order[0]), None


def _operator_config(config: GeneratorConfig, operator_id: str) -> Mapping[str, Any]:
    if operator_id == "OP-DUPLICATE_PAYMENT":
        return config.mutation_raw["duplicate_payment"]
    if operator_id == "OP-PARTIAL_PAYMENT_ALLOCATION":
        return config.mutation_raw["partial_payment_allocation"]
    raise ConfigError("unknown operator id", operator_id=operator_id)


def _schema_versions() -> dict[str, str]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "contracts" / "version.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(sorted(data["schemas"].items()))


def _episode_id(master_seed: str, config: GeneratorConfig, difficulty: str) -> str:
    token = sha256_hex(
        f"episode\x1f{master_seed}\x1f{config.config_hash}\x1f{difficulty}".encode("utf-8")
    )[:16].upper()
    return f"EP-{difficulty}-{token}"


def _commitment_salt(config_hash: str, episode_id: str) -> str:
    """Deterministic salt; stored sealed and only revealed with the truth."""
    return sha256_hex(f"salt\x1f{config_hash}\x1f{episode_id}".encode("utf-8"))


def _canaries(config_hash: str, episode_id: str, seed_digest: str) -> list[str]:
    """Internal leak-detection markers; they must never appear in public files."""
    return [
        hashlib.sha256(f"canary\x1f{part}\x1f{episode_id}".encode("utf-8")).hexdigest()[:32]
        for part in (config_hash[:16], seed_digest[:16], "truth", "provenance")
    ]


def _scan_public(files: Mapping[str, str], canaries: Sequence[str], config: GeneratorConfig) -> list[str]:
    """Canary + secret scan over public text. Any hit is a release blocker."""
    hits: list[str] = []
    seed_digest_tokens = [canary for canary in canaries]
    for name, text in files.items():
        lowered = text.lower()
        for token in seed_digest_tokens:
            if token.lower() in lowered:
                hits.append(f"{name}:canary")
        for forbidden in ("truth_id", "provenance", "operator_id", "master_seed", "mutated"):
            if forbidden in lowered:
                hits.append(f"{name}:forbidden-token:{forbidden}")
    if hits:
        raise RejectError("public file canary scan failed", hits=hits)
    return []


def _row_count(file_name: str, book: Book) -> int:
    if file_name.endswith(".jsonl"):
        return len(book.rows(file_name[: -len(".jsonl")]))
    return 1


def build_episode_set(
    *,
    seeds: Sequence[str],
    config: GeneratorConfig,
    difficulty: str = "L1",
    anomaly_count: int | None = None,
) -> tuple[list[EpisodePackage], list[dict[str, Any]]]:
    """Build many episodes, returning successes and per-seed failure records."""
    episodes: list[EpisodePackage] = []
    failures: list[dict[str, Any]] = []
    for master_seed in seeds:
        try:
            episodes.append(
                build_episode(
                    master_seed=master_seed,
                    config=config,
                    difficulty=difficulty,
                    anomaly_count=anomaly_count,
                )
            )
        except RejectError as exc:
            failures.append({"seed_token": sha256_hex(master_seed)[:12], **exc.to_dict()})
    return episodes, failures
