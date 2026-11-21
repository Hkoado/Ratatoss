"""Tests for one PLARS selection round. All snapshots are synthetic examples."""

import random
import unittest
from dataclasses import replace

from ratatoss.plars_selection import (
    NO_CANDIDATE,
    WAIT_FOR_SLOT,
    Batch,
    Device,
    Route,
    SharedResource,
    Snapshot,
    select_assignments,
)

SIZE = 8_000_000  # 64,000,000 bits, so 64 Mbit/s moves one batch in 1,000 ms.
FAST = 64_000_000
HALF = 32_000_000
SLOW = 16_000_000


def device(device_id, verified=(), *, rx=(0,), tx=(0,), target=False, transmit=False,
           origin=False, eta=0, verify=0, online=True, reconciled=True):
    return Device(
        device_id=device_id, online=online, reconciled=reconciled,
        verified_batches=frozenset(verified), rx_slot_free_in_ms=tuple(rx),
        tx_slot_free_in_ms=tuple(tx), is_target=target, can_transmit=transmit,
        is_origin=origin, eta_ms=eta, verify_ms=verify,
    )


def origin(device_id="A", verified=(0,), **kwargs):
    return device(device_id, verified, transmit=True, origin=True, rx=(), **kwargs)


def batches(count=1):
    return tuple(Batch(index, SIZE) for index in range(count))


def keys(result):
    return [(item.source_id, item.target_id, item.batch_id) for item in result.selections]


def waiting(result):
    return [(item.target_id, item.reason) for item in result.waiting]


class EligibilityTests(unittest.TestCase):
    def test_only_ready_members_missing_unleased_batches_are_assigned(self):
        everyone = ("B", "C", "D", "E", "F", "G", "I")
        snapshot = Snapshot(
            batches=batches(2),
            devices=(
                origin(verified=(0, 1), tx=(0,) * 8),
                device("B", (0,), target=True, eta=7),
                device("C", target=False, eta=6),                 # No accepted offer.
                device("D", target=True, eta=5, online=False),
                device("E", target=True, eta=4, reconciled=False),
                device("F", target=True, eta=3),
                device("G", (0, 1), target=True, eta=2, rx=(0, 0)),
                device("H", (0, 1), tx=(0,), transmit=False),     # Forwarding not allowed.
                device("J", (0, 1), tx=(0,), transmit=True, reconciled=False),
                device("I", target=True, eta=1),                  # No permitted route.
            ),
            routes=tuple(Route("A", key, SLOW, 0) for key in everyone if key != "I") + tuple(
                Route(source, key, FAST, 0) for source in ("H", "J") for key in everyone
            ),
            leased=frozenset({("F", 0)}),
        )

        result = select_assignments(snapshot)

        self.assertEqual(keys(result), [("A", "B", 1), ("A", "F", 1)])
        self.assertEqual(waiting(result), [("I", NO_CANDIDATE)])

    def test_never_assigns_a_batch_the_target_already_verified(self):
        snapshot = Snapshot(
            batches=batches(3),
            devices=(origin(verified=(0, 1, 2), tx=(0, 0, 0)),
                     device("B", (0, 2), target=True, rx=(0, 0, 0))),
            routes=(Route("A", "B", FAST, 0),),
        )
        self.assertEqual(keys(select_assignments(snapshot)), [("A", "B", 1)])

    def test_empty_job_selects_nothing(self):
        snapshot = Snapshot(batches=(), devices=(origin(verified=()), device("B", target=True)),
                            routes=(Route("A", "B", FAST, 0),))
        result = select_assignments(snapshot)
        self.assertEqual((result.selections, result.waiting), ((), ()))


class ContentionTests(unittest.TestCase):
    def test_largest_eta_target_takes_the_contended_slot_and_others_wait(self):
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(0,)), device("B", target=True, eta=5_000),
                     device("C", target=True, eta=9_000)),
            routes=(Route("A", "B", FAST, 0), Route("A", "C", FAST, 0)),
        )
        result = select_assignments(snapshot)
        self.assertEqual(keys(result), [("A", "C", 0)])
        self.assertEqual(waiting(result), [("B", WAIT_FOR_SLOT)])

    def test_routes_sharing_a_wan_split_its_remaining_budget(self):
        wan = ("a-uplink", "branch-wan")
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(0, 0)), device("B", target=True, eta=1),
                     device("C", target=True, eta=2)),
            routes=(Route("A", "B", FAST, 100, wan=True, resources=wan),
                    Route("A", "C", FAST, 100, wan=True, resources=wan)),
            resources=(SharedResource("a-uplink", 1_000_000_000),
                       SharedResource("branch-wan", FAST + HALF)),
        )
        result = select_assignments(snapshot)
        self.assertEqual(keys(result), [("A", "C", 0), ("A", "B", 0)])
        self.assertEqual([item.goodput_bps for item in result.selections], [FAST, HALF])
        self.assertEqual([item.finish_in_ms for item in result.selections], [1_100, 2_100])
        self.assertLessEqual(sum(item.goodput_bps for item in result.selections), FAST + HALF)

    def test_two_sources_never_lease_the_same_key(self):
        snapshot = Snapshot(
            batches=batches(2),
            devices=(origin(verified=(0, 1), tx=(0, 0)),
                     device("B", (0,), transmit=True, tx=(0,)),
                     device("C", target=True, rx=(0, 0, 0))),
            routes=(Route("A", "C", SLOW, 0, wan=True), Route("B", "C", FAST, 0)),
        )
        result = select_assignments(snapshot)
        self.assertEqual(keys(result), [("B", "C", 0), ("A", "C", 1)])

        leased = select_assignments(replace(snapshot, leased=frozenset({("C", 1)})))
        self.assertEqual(keys(leased), [("B", "C", 0)])

    def test_each_selection_reserves_the_target_receive_slot(self):
        snapshot = Snapshot(
            batches=batches(3),
            devices=(origin(verified=(0, 1, 2), tx=(0, 0, 0)), device("B", target=True, rx=(0,))),
            routes=(Route("A", "B", FAST, 0),),
        )
        result = select_assignments(snapshot)
        self.assertEqual(keys(result), [("A", "B", 0)])
        self.assertEqual(waiting(result), [("B", WAIT_FOR_SLOT)])

    def test_exhausted_route_budget_falls_back_to_another_source(self):
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(0,)), device("C", (0,), transmit=True, tx=(0,)),
                     device("B", target=True)),
            routes=(Route("A", "B", FAST, 0, wan=True, resources=("branch-wan",)),
                    Route("C", "B", SLOW, 0)),
            resources=(SharedResource("branch-wan", 0),),
        )
        self.assertEqual(keys(select_assignments(snapshot)), [("C", "B", 0)])

        without_peer = replace(snapshot, routes=snapshot.routes[:1])
        result = select_assignments(without_peer)
        self.assertEqual((keys(result), waiting(result)), ([], [("B", NO_CANDIDATE)]))


class RouteChoiceTests(unittest.TestCase):
    def snapshot(self, origin_goodput, peer_goodput, tolerance_ms=0):
        return Snapshot(
            batches=batches(),
            devices=(origin(tx=(0,)), device("B", (0,), transmit=True, tx=(0,)),
                     device("D", target=True, verify=50)),
            routes=(Route("A", "D", origin_goodput, 200, wan=True),
                    Route("B", "D", peer_goodput, 200, wan=True)),
            tolerance_ms=tolerance_ms,
        )

    def test_remote_target_picks_the_origin_when_it_is_faster(self):
        result = select_assignments(self.snapshot(FAST, SLOW))
        self.assertEqual(keys(result), [("A", "D", 0)])
        self.assertEqual(result.selections[0].finish_in_ms, 200 + 1_000 + 50)
        self.assertEqual(result.selections[0].origin_bytes, SIZE)

    def test_remote_target_picks_the_peer_when_it_is_faster(self):
        self.assertEqual(keys(select_assignments(self.snapshot(SLOW, FAST))), [("B", "D", 0)])

    def test_equal_paths_prefer_fewer_origin_bytes(self):
        self.assertEqual(keys(select_assignments(self.snapshot(FAST, FAST))), [("B", "D", 0)])

    def test_tolerance_prefers_fewer_wan_bytes(self):
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(0,)), device("B", (0,), transmit=True, tx=(0,)),
                     device("C", target=True)),
            routes=(Route("A", "C", FAST, 0, wan=True), Route("B", "C", FAST, 100)),
            tolerance_ms=100,
        )
        self.assertEqual(keys(select_assignments(snapshot)), [("B", "C", 0)])
        self.assertEqual(keys(select_assignments(replace(snapshot, tolerance_ms=99))),
                         [("A", "C", 0)])

    def test_fewer_wan_bytes_outrank_fewer_origin_bytes(self):
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(0,)), device("B", (0,), transmit=True, tx=(0,)),
                     device("C", target=True)),
            routes=(Route("A", "C", FAST, 0), Route("B", "C", FAST, 0, wan=True)),
        )
        result = select_assignments(snapshot)
        self.assertEqual(keys(result), [("A", "C", 0)])
        self.assertEqual((result.selections[0].wan_bytes, result.selections[0].origin_bytes),
                         (0, SIZE))

    def test_full_ties_use_batch_then_source_id(self):
        snapshot = Snapshot(
            batches=batches(2),
            devices=(device("P", (0, 1), transmit=True, tx=(0,)),
                     device("Q", (0, 1), transmit=True, tx=(0,)),
                     device("T", target=True)),
            routes=(Route("Q", "T", FAST, 0), Route("P", "T", FAST, 0)),
        )
        self.assertEqual(keys(select_assignments(snapshot)), [("P", "T", 0)])

    def test_waits_for_a_busy_fast_slot_instead_of_a_slower_path(self):
        snapshot = Snapshot(
            batches=batches(),
            devices=(origin(tx=(500,)), device("B", (0,), transmit=True, tx=(0,)),
                     device("D", target=True)),
            routes=(Route("A", "D", FAST, 0), Route("B", "D", SLOW, 0)),
        )
        result = select_assignments(snapshot)
        self.assertEqual((keys(result), waiting(result)), ([], [("D", WAIT_FOR_SLOT)]))

        # A spare receive slot must not let the slower path take the held batch.
        spare = replace(snapshot, devices=snapshot.devices[:2] + (
            device("D", target=True, rx=(0, 0)),))
        result = select_assignments(spare)
        self.assertEqual((keys(result), waiting(result)), ([], [("D", WAIT_FOR_SLOT)]))

        long_wait =replace(snapshot, devices=(origin(tx=(5_000,)),) + snapshot.devices[1:])
        self.assertEqual(keys(select_assignments(long_wait)), [("B", "D", 0)])


class BusyFastPathTests(unittest.TestCase):
    """A busy faster path keeps its batch, while free slots take other batches."""

    def snapshot(self, rx=(0, 0), resources=(), shared=()):
        return Snapshot(
            batches=batches(2),
            devices=(origin(verified=(0, 1), tx=(500,)),
                     device("B", (1,), transmit=True, tx=(0,)),
                     device("D", target=True, rx=rx)),
            routes=(Route("A", "D", FAST, 0, resources=shared),
                    Route("B", "D", 40_000_000, 0, resources=shared)),
            resources=resources,
        )

    def test_free_slot_takes_another_batch_while_the_faster_path_is_busy(self):
        result = select_assignments(self.snapshot())
        self.assertEqual(keys(result), [("B", "D", 1)])
        self.assertEqual(result.selections[0].finish_in_ms, 1_600)
        self.assertEqual(waiting(result), [("D", WAIT_FOR_SLOT)])

    def test_single_receive_slot_waits_when_granting_would_delay_the_faster_path(self):
        result = select_assignments(self.snapshot(rx=(0,)))
        self.assertEqual((keys(result), waiting(result)), ([], [("D", WAIT_FOR_SLOT)]))

    def test_grant_now_must_not_take_bandwidth_the_faster_path_needs(self):
        shared = ("d-downlink",)
        result = select_assignments(self.snapshot(
            resources=(SharedResource("d-downlink", FAST),), shared=shared))
        self.assertEqual((keys(result), waiting(result)), ([], [("D", WAIT_FOR_SLOT)]))


class DeterminismTests(unittest.TestCase):
    def test_input_order_does_not_change_the_result(self):
        wan = ("a-uplink", "branch-wan")
        snapshot = Snapshot(
            batches=batches(4),
            devices=(
                origin(verified=(0, 1, 2, 3), tx=(0, 0)),
                device("B", (0,), target=True, transmit=True, eta=8_000, tx=(0,), rx=(0, 0)),
                device("C", (1,), target=True, transmit=True, eta=8_000, tx=(0,), rx=(0, 0)),
                device("D", target=True, eta=12_000, rx=(0, 0)),
            ),
            routes=(
                Route("A", "B", FAST, 100, wan=True, resources=wan),
                Route("A", "C", FAST, 100, wan=True, resources=wan),
                Route("A", "D", HALF, 300, wan=True, resources=("a-uplink",)),
                Route("B", "C", FAST, 20), Route("C", "B", FAST, 20),
                Route("B", "D", SLOW, 300, wan=True, resources=("branch-wan",)),
                Route("C", "D", SLOW, 300, wan=True, resources=("branch-wan",)),
            ),
            resources=(SharedResource("a-uplink", FAST + HALF), SharedResource("branch-wan", FAST)),
            leased=frozenset({("D", 3)}),
            tolerance_ms=50,
        )
        expected = select_assignments(snapshot)
        self.assertTrue(expected.selections)

        shuffle = random.Random(21)
        for _ in range(20):
            fields = {}
            for name in ("batches", "devices", "routes", "resources"):
                items = list(getattr(snapshot, name))
                shuffle.shuffle(items)
                fields[name] = tuple(items)
            with self.subTest(order=[item.device_id for item in fields["devices"]]):
                self.assertEqual(select_assignments(replace(snapshot, **fields)), expected)


class ValidationTests(unittest.TestCase):
    def test_rejects_invalid_snapshots(self):
        good = Snapshot(
            batches=batches(),
            devices=(origin(), device("B", target=True)),
            routes=(Route("A", "B", FAST, 0, resources=("wan",)),),
            resources=(SharedResource("wan", FAST),),
        )
        select_assignments(good)
        bad = {
            "boolean tolerance": replace(good, tolerance_ms=True),
            "negative tolerance": replace(good, tolerance_ms=-1),
            "zero batch size": replace(good, batches=(Batch(0, 0),)),
            "duplicate batch": replace(good, batches=batches() * 2),
            "duplicate device": replace(good, devices=good.devices + (device("B"),)),
            "unknown verified batch": replace(good, devices=(origin(verified=(1,)), good.devices[1])),
            "float slot": replace(good, devices=(origin(tx=(0.0,)), good.devices[1])),
            "list slots": replace(good, devices=(replace(good.devices[0], tx_slot_free_in_ms=[0]),
                                                 good.devices[1])),
            "zero goodput": replace(good, routes=(Route("A", "B", 0, 0),)),
            "self route": replace(good, routes=(Route("A", "A", FAST, 0),)),
            "unknown route device": replace(good, routes=(Route("A", "Z", FAST, 0),)),
            "unknown resource": replace(good, routes=(Route("A", "B", FAST, 0, resources=("x",)),)),
            "duplicate route": replace(good, routes=good.routes * 2),
            "unknown lease": replace(good, leased=frozenset({("B", 9)})),
            "set lease": replace(good, leased={("B", 0)}),
        }
        for name, snapshot in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                select_assignments(snapshot)


if __name__ == "__main__":
    unittest.main()
