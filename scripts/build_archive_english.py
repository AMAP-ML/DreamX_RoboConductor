#!/usr/bin/env python3
"""Compile translated text templates into per-episode English display files."""
import argparse,collections,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CN=re.compile('[\u3400-\u9fff]');PLACEHOLDER=re.compile(r'\{V\d+\}')
def jp(path):
 raw=path.read_text();return json.loads(raw[raw.index('(')+1:raw.rfind(')')])
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);a=ap.parse_args();work=a.work
 units={u['id']:u for u in json.loads((work/'units.json').read_text())};refs=json.loads((work/'references.json').read_text());translations={}
 for path in sorted(work.glob('worker-*/output-*.json')):
  batch=json.loads(path.read_text());source={u['id']:u for u in json.loads(path.with_name(path.name.replace('output-','input-')).read_text())}
  if set(batch)!=set(source):raise ValueError('Incomplete batch: '+str(path))
  for key,value in batch.items():
   if not isinstance(value,str) or not value.strip() or CN.search(value):raise ValueError('Untranslated unit '+key)
   if collections.Counter(PLACEHOLDER.findall(value))!=collections.Counter(PLACEHOLDER.findall(units[key]['source'])):raise ValueError('Placeholder mismatch '+key)
   if key in translations and translations[key]!=value:raise ValueError('Conflicting translation '+key)
   translations[key]=value
 missing=set(units)-set(translations)
 if missing:raise ValueError(f'{len(missing)} translation units remain')
 source_translation={}
 for source in json.loads((work/'source.json').read_text()):
  pieces=[]
  for part in refs[source['id']]:
   if 'text' in part:pieces.append(part['text']);continue
   values=part['values'];text=PLACEHOLDER.sub(lambda m:values[int(m[0][2:-1])],translations[part['id']]);pieces.append(text+part['end'])
  result=''.join(pieces)
  if CN.search(result):raise ValueError('Chinese remains in '+source['id'])
  source_translation[source['text']]=result
 def tr(value):
  if isinstance(value,str) and CN.search(value):return source_translation[value]
  return value
 archive=ROOT/'dist/archive';raw=(archive/'catalog.js').read_text();catalog=json.loads(raw.split('=',1)[1].strip().rstrip(';'))
 out=archive/'translations/en';out.mkdir(parents=True,exist_ok=True);index=[]
 for platform in catalog['platforms']:
  for task in platform['tasks']:
   for entry in task['episodes']:
    path=archive/entry['data_file'];record=jp(path)
    localized={'id':record['id'],'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'manualSourceSha256':record.get('manual',{}).get('sha256'),
      'instruction':tr(record.get('instruction','')),'public_summary':tr(record.get('public_summary','')),'done_reason':tr(record.get('done_reason')),
      'warnings':[tr(v) for v in record.get('warnings',[])],
      'manual':{'text':tr(record.get('manual',{}).get('text','')),'media':[{'label':tr(m.get('label'))} for m in record.get('manual',{}).get('media',[])]},
      'steps':[{'narration':[tr(n) for n in s.get('narration',[])],'done_reason':tr(s.get('done_reason'))} for s in record.get('steps',[])]}
    target=out/(record['id']+'.json');target.write_text(json.dumps(localized,ensure_ascii=False,separators=(',',':'))+'\n');index.append({'id':record['id'],'source':entry['data_file'],'sourceSha256':localized['sourceSha256'],'translation':target.relative_to(archive).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
 (out/'index.json').write_text(json.dumps({'language':'en','episodes':len(index),'units':len(units),'entries':index},indent=1)+'\n')
 print(json.dumps({'episodes':len(index),'uniqueTranslatedUnits':len(units),'translatedSourceStrings':len(source_translation)}))
if __name__=='__main__':main()
