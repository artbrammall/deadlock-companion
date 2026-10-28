import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from recognition import HeroRecognizer

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'tests' / 'samples' / 'faded_normal'


class FadedNormalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = HeroRecognizer(ROOT / 'portraits')
        cls.layout = json.loads((ROOT / 'screen_config.json').read_text())['layouts']['ranked']
        cls.cases = json.loads((SAMPLES / 'cases.json').read_text())

    def test_recorded_normal_views_without_tab(self):
        complete = 0
        for case in self.cases:
            frame = np.zeros((990, 1760, 3), np.uint8)
            frame[:88] = cv2.imread(str(SAMPLES / case['file']))
            teams = self.recognizer.recognize_teams(frame, self.layout)
            with self.subTest(file=case['file']):
                self.assertEqual([r['hero'] for r in teams['ally']], case['ally'])
                labels = [r['hero'] for r in teams['enemy']]
                for actual, expected in zip(labels, case['enemy']):
                    self.assertIn(actual, (expected, 'UNKNOWN'))
                complete += labels == case['enemy']
        self.assertGreaterEqual(complete, 20)

    def test_constant_and_noise_rejected(self):
        rng = np.random.default_rng(157)
        images = [np.full((88, 74, 3), v, np.uint8) for v in (0, 80, 255)]
        images += [rng.integers(0, 256, (88, 74, 3), dtype=np.uint8) for _ in range(50)]
        for first in (False, True):
            for image in images:
                self.assertEqual(self.recognizer.recognize_local_contrast(image, first)['hero'], 'UNKNOWN')

    def test_one_fragment_cannot_identify_a_hero(self):
        rng = np.random.default_rng(23)
        for hero in ('haze', 'apollo', 'lash', 'billy', 'violet'):
            reference = cv2.resize(cv2.imread(str(ROOT / 'portraits' / f'{hero}.png')), (74, 88))
            for x, y in ((12, 8), (36, 8), (12, 36), (38, 58)):
                image = rng.integers(0, 256, (88, 74, 3), dtype=np.uint8)
                image[y:y+24, x:x+24] = reference[y:y+24, x:x+24]
                for first in (False, True):
                    with self.subTest(hero=hero, x=x, y=y, first=first):
                        self.assertEqual(self.recognizer.recognize_local_contrast(image, first)['hero'], 'UNKNOWN')

    def test_nonportrait_scene_crops_rejected(self):
        # Real HUD scenery from between portraits and outside both teams.
        for case in self.cases:
            hud = cv2.imread(str(SAMPLES / case['file']))
            for x in (0, 100, 180, 1500, 1600):
                for first in (False, True):
                    result = self.recognizer.recognize_local_contrast(hud[:, x:x+74], first)
                    self.assertEqual(result['hero'], 'UNKNOWN', (case['file'], x, result))

    def test_contrast_changes_and_sharp_background(self):
        yy, xx = np.mgrid[:88, :74]
        background = np.where(xx < 31, 25, 220).astype(np.float32)
        for hero in ('haze', 'apollo', 'lash', 'billy', 'violet'):
            reference = cv2.resize(cv2.imread(str(ROOT / 'portraits' / f'{hero}.png')), (74, 88))
            image = np.clip(reference.astype(np.float32)*0.3 + background[..., None]*0.7, 0, 255).astype(np.uint8)
            for first in (False, True):
                with self.subTest(hero=hero, first=first):
                    self.assertEqual(self.recognizer.recognize_local_contrast(image, first)['hero'], hero)


if __name__ == '__main__':
    unittest.main()
