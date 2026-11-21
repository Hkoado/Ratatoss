"""Check whether a batch fits the configured transfer budget."""

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class LeaseBudget:
    transfer_ms: int
    required_ms: int
    available_ms: int

    @property
    def fits(self) -> bool:
        return self.required_ms <= self.available_ms


def evaluate_lease_budget(
    *,
    batch_bytes: int,
    min_goodput_bps: int,
    remaining_lease_ms: int,
    remaining_adapter_ms: int,
    remaining_setup_ms: int,
    verify_commit_ms: int,
    margin_ms: int,
) -> LeaseBudget:
    """Evaluate a fixed budget immediately before grant or spawn.

    Supply the time left on each deadline and only setup yet to occur.
    The caller owns the monotonic deadlines.
    """
    for field, value, minimum in (
        ("batch-bytes", batch_bytes, 1),
        ("min-goodput-bps", min_goodput_bps, 1),
        ("remaining-lease-ms", remaining_lease_ms, 0),
        ("adapter-timeout-ms", remaining_adapter_ms, 0),
        ("setup-ms", remaining_setup_ms, 0),
        ("verify-commit-ms", verify_commit_ms, 0),
        ("margin-ms", margin_ms, 0),
    ):
        if type(value) is not int or value < minimum:
            raise ValueError(f"--{field} must be an integer >= {minimum}")

    transfer_ms = (batch_bytes * 8 * 1000 + min_goodput_bps - 1) // min_goodput_bps
    return LeaseBudget(
        transfer_ms=transfer_ms,
        required_ms=transfer_ms + remaining_setup_ms + verify_commit_ms + margin_ms,
        available_ms=min(remaining_lease_ms, remaining_adapter_ms),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-bytes", required=True, type=int)
    parser.add_argument("--min-goodput-bps", required=True, type=int)
    parser.add_argument("--remaining-lease-ms", required=True, type=int)
    parser.add_argument("--adapter-timeout-ms", dest="remaining_adapter_ms", required=True, type=int)
    parser.add_argument("--setup-ms", dest="remaining_setup_ms", required=True, type=int)
    parser.add_argument("--verify-commit-ms", required=True, type=int)
    parser.add_argument("--margin-ms", required=True, type=int)
    try:
        budget = evaluate_lease_budget(**vars(parser.parse_args()))
    except ValueError as exc:
        parser.error(str(exc))

    print(
        f"{'feasible' if budget.fits else 'infeasible'} "
        f"transfer_ms={budget.transfer_ms} required_ms={budget.required_ms} "
        f"available_ms={budget.available_ms}"
    )
    return 0 if budget.fits else 1


if __name__ == "__main__":
    raise SystemExit(main())
