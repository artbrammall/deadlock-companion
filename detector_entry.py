"""Console-capable worker; QProcess redirects its pipes without a terminal UI."""
import json
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace', write_through=True)
    if '--self-test' in sys.argv:
        # Exercise packaged imports and assets without capture or network traffic.
        import cv2
        import dxcam
        import httpx
        from app_paths import ASSET_DIR
        from recognition import HeroRecognizer
        from screen_state import ScreenStateDetector
        from ranked_gate import RankedPregameGate
        from stats_cache import load_scorer
        from real_opportunity import RealOpportunityScorer
        HeroRecognizer(ASSET_DIR / 'portraits')
        ScreenStateDetector(ASSET_DIR / 'screen_templates')
        RankedPregameGate(ASSET_DIR / 'screen_templates')
        json.loads((ASSET_DIR / 'screen_config.json').read_text())
        json.loads((ASSET_DIR / 'hero_ids.json').read_text())
        print('FORESIGHT_WORKER_OK', flush=True)
        return
    from app_paths import ensure_data
    ensure_data()
    import live_detection  # Existing capture loop and stdin stop protocol.


if __name__ == '__main__':
    main()
