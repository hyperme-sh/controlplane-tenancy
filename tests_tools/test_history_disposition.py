import hashlib
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_history_review as history


def fixture():
    row = {'object': 'a', 'path': 'old.py',
           'blob_sha256': hashlib.sha256(b'old').hexdigest(),
           'content_sha256': hashlib.sha256(b'old').hexdigest(),
           'classification': 'retained-payment-schema',
           'disposition': 'retained-not-cleared-for-publication'}
    return {'history_findings': [dict(row)]}, {'publication_cleared': False, 'findings': [row]}


def test_exact_retained_content_is_not_publication_clearance(monkeypatch):
    report, ledger = fixture()
    monkeypatch.setattr(history.subprocess, 'check_output', lambda *a: b'old')
    assert history.verify(report, ledger) == {'reviewed_coordinates': 1, 'publication_cleared': False}


@pytest.mark.parametrize('change', ['new', 'missing', 'duplicate', 'bytes', 'classification', 'disposition', 'clearance'])
def test_changed_history_or_disposition_is_refused(monkeypatch, change):
    report, ledger = fixture()
    monkeypatch.setattr(history.subprocess, 'check_output', lambda *a: b'changed' if change == 'bytes' else b'old')
    if change == 'new': report['history_findings'].append({'object': 'b', 'path': 'new.py'})
    if change == 'missing': report['history_findings'] = []
    if change == 'duplicate': ledger['findings'] *= 2
    if change == 'classification': ledger['findings'][0]['classification'] = 'unknown'
    if change == 'disposition': ledger['findings'][0]['disposition'] = 'publish'
    if change == 'clearance': ledger['publication_cleared'] = True
    with pytest.raises(ValueError): history.verify(report, ledger)
