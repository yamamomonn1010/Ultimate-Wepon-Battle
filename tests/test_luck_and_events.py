"""MVP第2段階の運、イベント設定、勝敗への反映を検証する。"""

from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

from game.battle import Weapon, load_element_rules, resolve_battle, score_weapon_luck
from game.events import EVENTS_PATH, load_event_rules, select_event


class LuckAndEventTests(TestCase):
    def setUp(self) -> None:
        self.rules = load_element_rules()
        self.events = load_event_rules()
        self.weapon = Weapon("左", "水", "自分の体力を回復する")

    def test_weapon_luck_is_derived_from_normalized_name(self) -> None:
        for name in ("武器1", "鏡", "やかん"):
            with self.subTest(name=name):
                expected = sha256(name.encode("utf-8")).digest()[-1] % 2
                self.assertEqual(score_weapon_luck(name), expected)
                self.assertEqual(score_weapon_luck(name), expected)
        self.assertEqual(score_weapon_luck("　武器１　"), score_weapon_luck("武器1"))

    def test_recognized_luck_ability_adds_one_point_without_changing_draws(self) -> None:
        lucky = replace(self.weapon, ability="自分の運を上げる")
        negated = replace(self.weapon, ability="自分の運を上げることはできない")
        result = resolve_battle(lucky, negated, self.rules, seed=0, events=self.events)
        assert result.scores is not None
        first, second = result.scores
        self.assertEqual(result.ability_analyses[0].main_effect, "運操作")
        self.assertEqual((first.ability_luck_points, second.ability_luck_points), (1, 0))
        self.assertEqual(first.weapon_luck_points, second.weapon_luck_points)
        self.assertEqual((first.match_luck_points, second.match_luck_points), (0, 0))
        self.assertEqual(first.total - second.total, 1)

    def test_generated_seed_can_reproduce_result(self) -> None:
        with patch("game.battle.randbits", return_value=795):
            original = resolve_battle(self.weapon, replace(self.weapon, element="炎"), self.rules)
        self.assertEqual(original.seed, 795)
        self.assertEqual(original.event_id, "meteor")
        self.assertEqual(
            original,
            resolve_battle(self.weapon, replace(self.weapon, element="炎"), self.rules, seed=original.seed),
        )

    def test_event_probability_boundaries_and_at_most_one_event(self) -> None:
        selected_ids = []
        for roll in range(1, 101):
            event = select_event(self.events, roll, score_gap=1)
            selected_ids.append(event.id if event else None)
        self.assertEqual(
            selected_ids[:6],
            ["referee_sneeze", "referee_sneeze", "referee_sneeze", "awakening", "meteor", None],
        )
        self.assertIsNone(selected_ids[-1])
        self.assertEqual(Counter(selected_ids), {"referee_sneeze": 3, "awakening": 1, "meteor": 1, None: 95})

    def test_unmet_event_conditions_do_not_try_the_next_event(self) -> None:
        for roll, gap in ((4, 0), (4, 2), (5, 0)):
            with self.subTest(roll=roll, gap=gap):
                self.assertIsNone(select_event(self.events, roll, score_gap=gap))

        luck_random = Mock()
        event_random = Mock()
        luck_random.randint.side_effect = (0, 0)
        event_random.randint.return_value = 4
        with patch("game.battle.Random", side_effect=(luck_random, event_random)):
            result = resolve_battle(self.weapon, self.weapon, self.rules, seed=0, events=self.events)
        self.assertIsNone(result.event_id)
        self.assertIsNone(result.adjusted_scores)
        self.assertEqual(luck_random.randint.call_args_list, [call(0, 1), call(0, 1)])
        event_random.randint.assert_called_once_with(1, 100)

    def test_sneeze_leaves_scores_and_outcome_unchanged(self) -> None:
        opponent = replace(self.weapon, element="炎")
        normal = resolve_battle(self.weapon, opponent, self.rules, seed=77, events=())
        event = resolve_battle(self.weapon, opponent, self.rules, seed=77, events=self.events)
        self.assertEqual(event.event_id, "referee_sneeze")
        self.assertEqual(event.scores, normal.scores)
        self.assertEqual(event.final_outcome, normal.final_outcome)
        self.assertIsNone(event.adjusted_scores)
        self.assertTrue(any("くしゃみ" in reason for reason in event.reasons))

    def test_awakening_recalculates_final_outcome_in_either_player_position(self) -> None:
        lucky = replace(self.weapon, ability="自分の運を上げる")
        for first, second, expected_winner, bonuses in (
            (lucky, self.weapon, "1P", (0, 1)),
            (self.weapon, lucky, "2P", (1, 0)),
        ):
            with self.subTest(expected_winner=expected_winner):
                result = resolve_battle(first, second, self.rules, seed=149, events=self.events)
                assert result.scores is not None and result.adjusted_scores is not None
                self.assertEqual(result.event_id, "awakening")
                self.assertEqual(result.provisional_outcome, expected_winner)
                self.assertEqual(result.final_outcome, "引き分け")
                self.assertEqual(tuple(score.event_points for score in result.scores), (0, 0))
                self.assertEqual(tuple(score.event_points for score in result.adjusted_scores), bonuses)
                self.assertEqual(tuple(score.total for score in result.adjusted_scores), (2, 2))

    def test_meteor_forces_draw_even_with_clear_score_advantage(self) -> None:
        result = resolve_battle(self.weapon, replace(self.weapon, element="炎"), self.rules, seed=795)
        assert result.scores is not None
        self.assertEqual(result.event_id, "meteor")
        self.assertEqual(tuple(score.total for score in result.scores), (3, 1))
        self.assertEqual(result.provisional_outcome, "1P")
        self.assertEqual(result.final_outcome, "引き分け")
        self.assertIsNone(result.adjusted_scores)
        self.assertIn("特殊イベントにより引き分け", result.reasons[-1])

    def test_explosion_skips_luck_and_event_draws(self) -> None:
        explosive = replace(self.weapon, ability="何があっても必ず勝つ")
        with (
            patch("game.battle.randbits") as seed_factory,
            patch("game.battle.Random") as random_factory,
            patch("game.battle.score_weapon_luck") as weapon_luck,
            patch("game.battle.load_event_rules") as event_loader,
            patch("game.battle.select_event") as event_selector,
        ):
            for opponent in (self.weapon, explosive):
                result = resolve_battle(explosive, opponent, self.rules)
                self.assertIsNone(result.event_id)
                self.assertIsNone(result.scores)
                self.assertIsNone(result.provisional_outcome)
            for mock in (seed_factory, random_factory, weapon_luck, event_loader, event_selector):
                mock.assert_not_called()


class EventConfigurationTests(TestCase):
    def test_zero_probability_and_changed_conditions_take_effect(self) -> None:
        config = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        config[0]["probability"] = 0
        config[1]["probability"] = 5
        config[1]["condition_value"] = 2
        with patch.object(Path, "read_text", return_value=json.dumps(config)):
            rules = load_event_rules()
        self.assertIsNone(select_event(rules, 1, score_gap=1))
        event = select_event(rules, 5, score_gap=2)
        assert event is not None
        self.assertEqual(event.id, "awakening")

    def test_invalid_event_configuration_is_rejected(self) -> None:
        original = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        cases = (
            (1, {"id": original[0]["id"]}),
            (0, {"probability": True}),
            (0, {"probability": 1.5}),
            (0, {"probability": -1}),
            (0, {"probability": 100}),
            (0, {"probability": 101}),
            (0, {"condition": "unsupported"}),
            (0, {"effect": "force_draw"}),
            (1, {"condition_value": -1}),
            (1, {"effect_value": 0}),
        )
        for index, changes in cases:
            with self.subTest(changes=changes):
                config = [dict(entry) for entry in original]
                config[index].update(changes)
                with patch.object(Path, "read_text", return_value=json.dumps(config)), self.assertRaises(ValueError):
                    load_event_rules()
