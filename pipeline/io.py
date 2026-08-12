import json,os,shutil,tempfile,uuid
from pathlib import Path
def atomic_json(path,data):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=p.name)
 try:
  with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def read_json(path,default=None):
 try:return json.loads(Path(path).read_text())
 except (OSError,json.JSONDecodeError):return default


class PublicationError(RuntimeError):
 """A staged data release could not be promoted safely."""


def staged_data_directory(public_dir=Path('public')):
 """Return a unique staging directory adjacent to ``public/data``."""
 root=Path(public_dir)
 root.mkdir(parents=True,exist_ok=True)
 path=root/f'.data-stage-{uuid.uuid4().hex}'
 path.mkdir()
 return path


def promote_data_directory(stage,target=Path('public/data')):
 """Promote a fully validated output set with rollback on rename failure.

 The caller must finish every fetch, transform, and contract validation before
 invoking this function.  No files are copied into the live directory one at a
 time, so removed v1 series cannot survive a v2 hard cut.
 """
 stage=Path(stage);target=Path(target)
 if not stage.is_dir() or not any(stage.iterdir()):
  raise PublicationError('staged data directory is missing or empty')
 if stage.parent!=target.parent:
  raise PublicationError('stage and target must share a parent for rename promotion')
 backup=target.parent/f'.data-backup-{uuid.uuid4().hex}'
 moved_old=False
 try:
  if target.exists():
   os.replace(target,backup);moved_old=True
  os.replace(stage,target)
 except OSError as exc:
  if moved_old and backup.exists() and not target.exists():os.replace(backup,target)
  raise PublicationError(f'failed to promote staged data: {exc}') from exc
 finally:
  if stage.exists():shutil.rmtree(stage)
 if backup.exists():shutil.rmtree(backup)
