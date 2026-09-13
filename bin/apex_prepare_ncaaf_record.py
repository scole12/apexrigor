#!/usr/bin/env python3
"""Build the shared APEX-wide record from stable, already graded source books.

Called by the shared publisher under its publication lock. Reads sport products;
writes only the shared publisher's derived-results authority. No Git or email.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE_NAMES = ('apex_results_summary.json', 'nfl_results_archive.json',
                'nhl_results_archive.json', 'mma_results_archive.json', 'mma_results_summary.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + '\n')


def validate_book(book, receipt, slate_date):
    rows = [r for r in book['positions'] if r.get('slate_date') == slate_date]
    if (receipt.get('status') != 'PASS' or receipt.get('slate_date_et') != slate_date
            or book.get('latest_graded_slate') != slate_date
            or book.get('season_year') != receipt.get('season_year')
            or len(rows) == 0 or len(rows) != receipt.get('position_count')
            or len(rows) != receipt.get('final_position_count')
            or any(r.get('result') not in ('W', 'L', 'PUSH', 'VOID') for r in rows)
            or len({r['position_id'] for r in rows}) != len(rows)):
        raise RuntimeError('NCAA_SHARED_RECORD_GRADED_BOOK_MISMATCH')


def prepare(slate_date, *, state, site_data, output_root, fuse, render, implementation_hashes):
    date.fromisoformat(slate_date)
    product_path = state / 'results' / slate_date / 'GRADE_PRODUCTS_RECEIPT.json'
    product_bytes = product_path.read_bytes()
    product = json.loads(product_bytes)
    season = int(product['season_year'])
    cumulative = state / 'results' / f'NCAAF_CUMULATIVE_RESULTS_{season}.json'
    cumulative_bytes = cumulative.read_bytes()
    book = json.loads(cumulative_bytes)
    validate_book(book, product, slate_date)
    book_hash = hashlib.sha256(cumulative_bytes).hexdigest()
    if book_hash != product.get('results_summary_sha256'):
        raise RuntimeError('NCAA_SHARED_RECORD_PRODUCT_RECEIPT_MISMATCH')
    destination = output_root / slate_date
    if destination.exists():
        receipt = json.loads((destination / 'APEX_TOTAL_RECORD_RECEIPT.json').read_text())
        if (receipt.get('status') != 'VERIFIED_GENERATED_ARTIFACT'
                or receipt.get('slate_date_et') != slate_date
                or receipt.get('canonical_results_sha256') != book_hash
                or receipt.get('grade_products_receipt_sha256') != hashlib.sha256(product_bytes).hexdigest()
                or receipt.get('artifact_sha256') != sha(destination / f'APEX_TOTAL_RECORD_{slate_date.replace("-", "")}.png')
                or receipt.get('source_snapshot_sha256') != sha(destination / 'APEX_TOTAL_RECORD_SOURCE.json')):
            raise RuntimeError('NCAA_SHARED_RECORD_EXISTING_ARTIFACT_CONFLICT')
        return {'status': 'REUSED_VERIFIED_ARTIFACT', 'slate_date': slate_date, 'output': str(destination)}
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + slate_date + '-', dir=output_root))
    try:
        data = temporary / 'source_books'; data.mkdir()
        source_hashes = {}
        for name in SOURCE_NAMES:
            source = site_data / name
            body = source.read_bytes()
            source_hashes[str(source)] = hashlib.sha256(body).hexdigest()
            (data / name).write_bytes(body)
        (data / 'ncaaf_results_cumulative.json').write_bytes(cumulative_bytes)
        source_hashes[str(cumulative)] = book_hash
        source_hashes[str(product_path)] = hashlib.sha256(product_bytes).hexdigest()
        # A source changing during capture invalidates this attempt. The next
        # scheduled publisher run can capture a fresh, stable snapshot.
        if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
            raise RuntimeError('NCAA_SHARED_RECORD_INPUT_CHANGED_DURING_CAPTURE')
        fused = fuse(json.loads((data / 'apex_results_summary.json').read_text()), data_dir=data)
        if fused.get('latest_graded_date') != slate_date:
            raise RuntimeError('NCAA_SHARED_RECORD_OTHER_BOOK_DATE_MISMATCH')
        for key in ('wins', 'losses', 'pushes'):
            if int(fused['overall'][key]) != sum(int(fused['sports'][sport][key]) for sport in fused['sports_included']):
                raise RuntimeError('NCAA_SHARED_RECORD_AGGREGATE_MISMATCH')
        own = fused['sports']['ncaaf']
        if (int(own['wins']) != int(book['season_record']['W'])
                or int(own['losses']) != int(book['season_record']['L'])
                or int(own['positions_tracked']) != len(book['positions'])):
            raise RuntimeError('NCAA_SHARED_RECORD_NCAA_CONTRIBUTION_MISMATCH')
        snapshot = temporary / 'APEX_TOTAL_RECORD_SOURCE.json'; save(snapshot, fused)
        image = temporary / f'APEX_TOTAL_RECORD_{slate_date.replace("-", "")}.png'
        render(image, fused)
        from PIL import Image
        with Image.open(image) as picture:
            if (picture.info.get('RecordScope') != 'APEX_ALL_OFFICIAL_PRODUCTION_RESULTS'
                    or picture.info.get('ThroughDate') != slate_date
                    or any(int(picture.info.get(label, -1)) != int(fused['overall'][key])
                           for label, key in (('Wins', 'wins'), ('Losses', 'losses'), ('Pushes', 'pushes')))):
                raise RuntimeError('NCAA_SHARED_RECORD_RENDERED_SCOPE_MISMATCH')
        if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
            raise RuntimeError('NCAA_SHARED_RECORD_INPUT_CHANGED_DURING_RENDER')
        if any(sha(Path(path)) != digest for path, digest in implementation_hashes.items()):
            raise RuntimeError('NCAA_SHARED_RECORD_IMPLEMENTATION_CHANGED')
        receipt = {'status': 'VERIFIED_GENERATED_ARTIFACT', 'slate_date_et': slate_date,
                   'artifact_sha256': sha(image), 'source_snapshot_sha256': sha(snapshot),
                   'canonical_results_sha256': book_hash,
                   'grade_products_receipt_sha256': hashlib.sha256(product_bytes).hexdigest(),
                   'source_hashes': source_hashes, 'implementation_hashes': implementation_hashes,
                   'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                   'source': 'Frozen copies of shared saved books plus the exact NCAA grade-products book',
                   'engine_reruns': 0, 'email_sends': 0, 'sport_authority_writes': 0}
        save(temporary / 'APEX_TOTAL_RECORD_RECEIPT.json', receipt)
        for file in temporary.rglob('*'):
            if file.is_file():
                with file.open('rb') as stream:
                    os.fsync(stream.fileno())
        for folder in (data, temporary):
            descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.rename(temporary, destination)
        descriptor = os.open(output_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {'status': 'GENERATED_VERIFIED_ARTIFACT', 'slate_date': slate_date, 'output': str(destination),
                'artifact_sha256': receipt['artifact_sha256'], 'engine_reruns': 0, 'email_sends': 0}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--site-data', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path)
    args = parser.parse_args()
    runtime = Path('/opt/apex_ncaaf/current/production')
    shared = Path(__file__).resolve().parent
    implementations = {str(path.resolve()): sha(path) for path in (
        runtime / 'build_grade_products.py', shared / 'apex_total_results.py')}
    sys.path.insert(0, str(runtime)); sys.path.insert(0, str(shared))
    import build_grade_products as products
    import apex_total_results as total
    if any(sha(Path(path)) != digest for path, digest in implementations.items()):
        raise RuntimeError('NCAA_SHARED_RECORD_IMPLEMENTATION_CHANGED_DURING_IMPORT')
    result = prepare(args.date, state=args.state, site_data=args.site_data, output_root=args.output_root,
                     fuse=total.fuse_summary, render=products.render_apex_overall_png,
                     implementation_hashes=implementations)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
