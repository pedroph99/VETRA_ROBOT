import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from robot.controller import Controller
from robot.demo_scene import DemoScene
from robot.inference_client import HttpDetector, PhotoBank
from robot.state import State


class PhotoTests(unittest.TestCase):
    def test_samples_only_the_requested_crop(self):
        bank = PhotoBank(rng=random.Random(12))
        for crop, prefix in [
            ("Tomate", "Tomato"),
            ("Pimentão", "Pepper,_bell"),
            ("Morango", "Strawberry"),
        ]:
            draws = [bank.choose(crop) for _ in range(60)]
            self.assertTrue(
                all(row["label"].startswith(prefix + "___") for row in draws)
            )
            self.assertGreater(len({row["file"] for row in draws}), 1)
        self.assertIsNone(bank.choose("Alface"))

    def test_unsupported_crop_does_not_send_any_photo(self):
        detector = HttpDetector("http://127.0.0.1:1")
        with patch("robot.inference_client.urlopen") as send:
            result = detector.analyze(Path("unused.png"), {"crop": "Alface", "capture":
                {"analysis_state": "unsupported_crop"}})
        send.assert_not_called()
        self.assertEqual(result["analysis_state"], "unsupported_crop")
        self.assertIsNone(result["confidence"])

    def test_transmission_excludes_ground_truth_and_scenario(self):
        import io
        import json

        bank = PhotoBank(rng=random.Random(1))
        expected = dict(status="NORMAL", top5=[], predicted_class="Tomato___healthy")
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'images').mkdir()
            scene = DemoScene(SimpleNamespace(data_dir=Path(directory)))
            capture = scene.capture_for_model({'crop': 'Tomate', 'id': 2, 'scenario': 'whitefly'}, 'capture', bank)
            original = Path(directory) / 'images' / capture['filename']
            with patch(
                "robot.inference_client.urlopen",
                return_value=io.BytesIO(json.dumps(expected).encode()),
            ) as send:
                result = HttpDetector("http://test", bank).analyze(
                    original, {"crop": "Tomate", "scenario": "whitefly", "capture": capture}
                )
            request = send.call_args.args[0]
            self.assertEqual(
                request.full_url, "http://test/api/classification/predict?crop=Tomate"
            )
            self.assertNotIn(b"whitefly", request.data)
            self.assertEqual(result["predicted_class"], "Tomato___healthy")
            self.assertTrue(
                (Path(directory) / 'images' / Path(result["analysis_image"]).name).exists()
            )
            self.assertEqual(request.data, original.read_bytes())
            self.assertEqual(result['analysis_image'], result['camera_image'])

    def test_scene_mode_sends_camera_crop_bytes(self):
        import io
        import json

        bank = PhotoBank(rng=random.Random(2))
        answer = dict(status='NORMAL', top5=[], predicted_class='Tomato___healthy')
        with tempfile.TemporaryDirectory() as directory:
            camera = Path(directory) / 'camera.png'
            crop = Path(directory) / 'camera-modelo.jpg'
            camera.write_bytes(b'original-camera-frame')
            crop.write_bytes(b'camera-crop-for-model')
            capture = dict(analysis_state='ready', analysis_file=crop.name,
                           capture_conditions={}, capture_quality={}, capture_attempts=1,
                           photo_provenance={'dataset_label': 'Tomato___healthy'})
            with patch('robot.inference_client.urlopen', return_value=io.BytesIO(json.dumps(answer).encode())) as send:
                result = HttpDetector('http://test', bank).analyze(camera, {'crop': 'Tomate', 'capture': capture})
            self.assertEqual(send.call_args.args[0].data, crop.read_bytes())
            self.assertNotEqual(send.call_args.args[0].data, camera.read_bytes())
            self.assertEqual(result['camera_image'], '/images/camera.png')
            self.assertEqual(result['analysis_image'], '/images/camera-modelo.jpg')

    def test_bad_capture_is_retried_before_inference(self):
        import io
        import json

        bank = PhotoBank(rng=random.Random(4))
        answer = dict(status='NORMAL', top5=[], predicted_class='Tomato___healthy')
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'images').mkdir()
            scene = DemoScene(SimpleNamespace(data_dir=Path(directory)))
            with patch('robot.capture_plan.assess_quality', side_effect=[
                dict(accepted=False, brightness=10, contrast=5, sharpness=3, reasons=['iluminação']),
                dict(accepted=True, brightness=100, contrast=30, sharpness=25, reasons=[]),
            ]):
                capture = scene.capture_for_model({'crop': 'Tomate', 'id': 2}, 'capture', bank)
            original = Path(directory) / 'images' / capture['filename']
            with patch('robot.inference_client.urlopen', return_value=io.BytesIO(json.dumps(answer).encode())) as send:
                result = HttpDetector('http://test', bank).analyze(original, {'crop': 'Tomate', 'capture': capture})
            self.assertEqual(result['capture_attempts'], 2)
            self.assertTrue(result['capture_quality']['accepted'])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0].headers['Content-type'], 'image/jpeg')

    def test_three_bad_captures_skip_inference(self):
        bank = PhotoBank(rng=random.Random(5))
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'images').mkdir()
            scene = DemoScene(SimpleNamespace(data_dir=Path(directory)))
            with patch('robot.capture_plan.assess_quality', return_value=dict(
                accepted=False, brightness=8, contrast=2, sharpness=1, reasons=['iluminação']
            )):
                capture = scene.capture_for_model({'crop': 'Tomate', 'id': 2, 'scenario': 'normal'}, 'capture', bank)
            original = Path(directory) / 'images' / capture['filename']
            with patch('robot.inference_client.urlopen') as send:
                result = HttpDetector('http://test', bank).analyze(original, {'crop': 'Tomate', 'capture': capture})
            send.assert_not_called()
            self.assertEqual(result['analysis_state'], 'poor_quality')
            self.assertEqual(result['capture_attempts'], 3)
            self.assertFalse(result['capture_quality']['accepted'])


class BackgroundTests(unittest.TestCase):
    def test_pause_resume_and_cancel_do_not_save_stale_result(self):
        import threading

        gate = threading.Event()

        class SlowDetector:
            background = True

            def analyze(self, image, bed):
                gate.wait(3)
                return dict(
                    status="NORMAL",
                    problem="Teste",
                    confidence=0.9,
                    detection="Teste",
                    simulated=False,
                )

        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory), demo=True)
            controller = Controller(state, DemoScene(state), SlowDetector())
            try:
                controller.command("START_MISSION")
                state.status = "INSPECTING"
                controller.tick(2)
                self.assertIsNotNone(controller.pending)
                controller.command("PAUSE_MISSION")
                gate.set()
                controller.pending[0].result(timeout=5)
                controller.tick(0.1)
                self.assertEqual(state.store.read("inspection", 10), [])
                controller.command("RESUME_MISSION")
                controller.tick(0.1)
                self.assertEqual(len(state.store.read("inspection", 10)), 1)
                state.status = "INSPECTING"
                controller.elapsed = 2
                controller.tick(0.1)
                controller.command("RETURN_HOME")
                controller.tick(0.1)
                self.assertIsNone(controller.pending)
                self.assertEqual(len(state.store.read("inspection", 10)), 1)
            finally:
                gate.set()
                controller.close()
                state.store.close()
