"""Extract the complete source artifact and exercise an actual fresh trial server."""
import hashlib
import json
import os
import re
import selectors
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_trial_package import build

def run():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);package=build(root/'trial.zip')
  with zipfile.ZipFile(package) as archive:
   archive.extractall(root/'extracted')
  app=root/'extracted/zhuanjiao-trial'
  manifest=json.loads((app/'package-manifest.json').read_text())
  for name,digest in manifest['sha256'].items():assert hashlib.sha256((app/name).read_bytes()).hexdigest()==digest,name
  process=subprocess.Popen([sys.executable,'Backend mission/server.py','--trial','--port','0','--data',str(root/'trial-data')],cwd=app,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
   assert selector.select(10),'trial server did not report startup'
   line=process.stdout.readline();match=re.search(r'port (\d+)',line)
   assert match,(line,process.stderr.read() if process.poll() is not None else '')
   base='http://127.0.0.1:'+match.group(1)
   def get(path):
    with urllib.request.urlopen(base+path,timeout=5) as response:return response.read()
   assert json.loads(get('/api/health'))=={'ok':True,'trial':True}
   assert json.loads(get('/api/config'))['auth_mode']=='password'
   assert json.loads(get('/api/products/search'))['items']==[]
   assert '转角' in get('/').decode()
   assert b'import' in get('/src/main.js')
   assert b'CatalogSearch' in (app/'Backend mission/app/catalog/search.py').read_bytes()
   print('Clean source ZIP passed: checksums, extraction, fresh trial startup, health/config/search and ES entry.')
  finally:
   process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()

if __name__=='__main__':run()
