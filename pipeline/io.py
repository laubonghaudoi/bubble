import json,os,tempfile
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
