"""Download original game hero cards for the UI, never recognition templates."""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'assets' / 'hero_portraits'
ENDPOINT = 'https://api.deadlock-api.com/v1/assets/heroes'


def decode_image(data):
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or min(image.shape[:2]) < 16:
        raise ValueError('Response is not a usable image')
    return image


def atomic_write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def main():
    mapping = json.loads((ROOT / 'hero_ids.json').read_text(encoding='utf-8-sig'))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('hero_ids.json must contain a nonempty name-to-ID mapping')
    for name, hero_id in mapping.items():
        if not re.fullmatch(r'[a-z0-9_]+', name) or type(hero_id) is not int:
            raise ValueError(f'Invalid hero mapping: {name!r}')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'source': ENDPOINT, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
              'artwork_credit': 'Deadlock hero artwork belongs to Valve Corporation. '
              'Provided via the independent community Deadlock API.', 'heroes': {}, 'errors': {}}
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        print('Fetching hero artwork metadata...', flush=True)
        response = client.get(ENDPOINT)
        response.raise_for_status()
        heroes = response.json()
        if not isinstance(heroes, list):
            raise ValueError('Expected a list of heroes from the asset API')
        by_id = {}
        for hero in heroes:
            if hero['id'] in by_id:
                raise ValueError(f"Duplicate API hero ID: {hero['id']}")
            by_id[hero['id']] = hero
        for index, (name, hero_id) in enumerate(sorted(mapping.items()), 1):
            print(f'[{index}/{len(mapping)}] {name}', flush=True)
            try:
                hero = by_id.get(hero_id)
                if hero is None:
                    raise ValueError(f'Hero ID {hero_id} is missing from the asset API')
                images = hero.get('images') or {}
                # Prefer hero cards. Use only URLs explicitly supplied by the API.
                candidates = [(key, images[key]) for key in
                              ('icon_hero_card', 'icon_hero_card_webp',
                               'selection_image', 'selection_image_webp')
                              if isinstance(images.get(key), str) and images[key].startswith('https://')]
                if not candidates:
                    raise ValueError(f'No hero card or selection image. Available fields: {sorted(images)}')
                problems = []
                for field, url in candidates:
                    try:
                        response = client.get(url)
                        response.raise_for_status()
                        decoded = decode_image(response.content)
                        # PNG is supported by Qt; preserve original dimensions and alpha.
                        ok, encoded = cv2.imencode('.png', decoded)
                        if not ok:
                            raise ValueError('Could not encode PNG')
                        content = encoded.tobytes()
                        atomic_write(OUTPUT / f'{name}.png', content)
                        report['heroes'][name] = {
                            'hero_id': hero_id, 'display_name': hero['name'],
                            'file': f'{name}.png', 'image_field': field, 'source_url': url,
                            'width': decoded.shape[1], 'height': decoded.shape[0],
                            'sha256': hashlib.sha256(content).hexdigest()}
                        break
                    except (httpx.HTTPError, ValueError, cv2.error) as error:
                        problems.append(f'{field}: {error}')
                else:
                    raise ValueError('; '.join(problems))
            except (httpx.HTTPError, ValueError, OSError, KeyError, cv2.error) as error:
                report['errors'][name] = str(error)
                print(f'  FAILED: {error}', flush=True)
    atomic_write(OUTPUT / 'manifest.json', (json.dumps(report, indent=2) + '\n').encode())
    atomic_write(OUTPUT / 'CREDITS.txt', (report['artwork_credit'] + '\nSource: ' + ENDPOINT + '\n').encode())
    print(f"\nDownloaded {len(report['heroes'])}/{len(mapping)} portraits to {OUTPUT}")
    print('Recognition templates in portraits/ were not changed.')
    if report['errors']:
        print('Some downloads failed. See manifest.json and rerun to retry.')
        return 1
    print('Done. These images are ready for the interface redesign.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (httpx.HTTPError, ValueError, OSError, KeyError, TypeError) as error:
        print(f'Download stopped: {error}', file=sys.stderr)
        sys.exit(1)
