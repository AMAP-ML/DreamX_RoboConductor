#!/usr/bin/env python3
"""Check full English display coverage against unchanged episode sources."""
from pathlib import Path
import hashlib,json,re
from release_privacy import scan_public_text
ROOT=Path(__file__).resolve().parents[1]
CN=re.compile('[\u3400-\u9fff]')
def read_episode(path):
 raw=path.read_text();return json.loads(raw[raw.index('(')+1:raw.rfind(')')])
def verify():
 archive=ROOT/'dist/archive';raw=(archive/'catalog.js').read_text();cat=json.loads(raw.split('=',1)[1].strip().rstrip(';'))
 expected={e['id']:e for p in cat['platforms'] for t in p['tasks'] for e in t['episodes']}
 index=json.loads((archive/'translations/en/index.json').read_text());assert index['episodes']==len(expected)
 entries={e['id']:e for e in index['entries']};assert set(entries)==set(expected)
 source_chinese=translated_strings=narrations=0
 def strings(value):
  if isinstance(value,str):yield value
  elif isinstance(value,list):
   for x in value:yield from strings(x)
  elif isinstance(value,dict):
   for x in value.values():yield from strings(x)
 for key,entry in entries.items():
  original_path=archive/expected[key]['data_file'];original=read_episode(original_path)
  target=archive/entry['translation'];payload=target.read_bytes();data=json.loads(payload)
  private=[finding for finding in scan_public_text({entry['translation']:payload}) if finding['type']!='experiment-record-id']
  assert not private, [(finding['file'],finding['line'],finding['type']) for finding in private]
  assert hashlib.sha256(original_path.read_bytes()).hexdigest()==entry['sourceSha256']==data['sourceSha256'],key
  assert hashlib.sha256(target.read_bytes()).hexdigest()==entry['sha256'],key
  assert data['id']==key and data['manualSourceSha256']==original['manual']['sha256'],key
  assert len(data['steps'])==len(original['steps']),key
  for source,dest in zip(original['steps'],data['steps']):
   assert len(dest['narration'])==len(source.get('narration',[])),key
   narrations+=len(dest['narration'])
  for value in strings(data):assert not CN.search(value),key;translated_strings+=1
  source_chinese+=sum(bool(CN.search(x)) for x in strings({'manual':original['manual']['text'],'summary':original.get('public_summary'),'steps':[s.get('narration') for s in original['steps']]}))
 return {'episodes':len(entries),'textStrings':translated_strings,'narrations':narrations,'originalChineseStringsPreserved':source_chinese,'status':'ok'}
if __name__=='__main__':print(json.dumps(verify()))
