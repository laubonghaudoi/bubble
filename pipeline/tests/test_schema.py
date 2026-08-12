import json
from pathlib import Path
ALLOWED_Q={'official','derived_official','public_vendor','proxy','manual','paid_required'}
ALLOWED_S={'ok','stale','missing','error','not_released','manual_update_due','paid_data_unavailable'}
def test_snapshot_schema_and_missing_not_zero():
 x=json.loads(Path('public/data/snapshot.json').read_text());assert x['schema_version']=='1.0.0'
 for m in x['metrics'].values():
  assert m['quality'] in ALLOWED_Q and m['status'] in ALLOWED_S
  if m['status'] in ('missing','paid_data_unavailable','manual_update_due'):assert m['value'] is None
def test_metric_knowledge_contract():
 x=json.loads(Path('public/data/manifest.json').read_text())
 required={'question_answered','why_track','false_positives','confirm_with','cannot_conclude'}
 for m in x['metrics']:assert required<=m.keys()
def test_series_provenance():
 for p in Path('public/data/series').glob('*.json'):
  x=json.loads(p.read_text());assert {'metric_id','status','quality','retrieved_at','knowledge','observations'}<=x.keys()
