#!/usr/bin/env python3
"""Merge redacted Piper cases. Defaults to plan-only; --apply writes outputs.
Metadata root must contain original record.json/events.jsonl/task_manual/codex files.
Never copy metadata frame files or native sessions into the published tree.
"""
import argparse, datetime, hashlib, json, pathlib, re, shutil, subprocess, sys, tempfile
from zoneinfo import ZoneInfo
SHANGHAI=ZoneInfo("Asia/Shanghai")
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/vendor'))
from visualizer.build import _episode, _summary, _json
from public_data_sanitizer import sanitize_public_data

def read(p):return json.loads(p.read_text())
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=1)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jsonp(p):
 s=p.read_text();return json.loads(s[s.index('{'):s.rfind('}')+1])
def stamp(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
def times(events,record):
 summary=record.get('summary',{}); result={}
 for key in ('duration_seconds','execution_duration_seconds'):
  value=summary.get(key,record.get(key))
  if isinstance(value,(int,float)) and value>=0:result[key]=value
 observed=[e for e in events if e.get('event') in ('start_episode','execute_turn','finish_episode') and e.get('time')]
 starts=[e for e in observed if e['event']=='start_episode'];ends=[e for e in observed if e['event']=='finish_episode']
 if starts and ends:
  elapsed=(stamp(ends[-1]['time'])-stamp(starts[0]['time'])).total_seconds()
  if elapsed<0:raise ValueError('Negative trace duration')
  result.setdefault('execution_duration_seconds',elapsed)
  result.setdefault('duration_seconds',elapsed)
 if 'execution_duration_seconds' not in result:raise ValueError('No measured execution duration; need start/finish trace timestamps or recorded summary')
 return result

def probe(binary,p,ffmpeg=None):
 if binary:
  return json.loads(subprocess.check_output([binary,'-v','error','-select_streams','v:0','-show_entries','stream=width,height:format=duration','-of','json',str(p)]))
 if not ffmpeg:raise ValueError('ffprobe or ffmpeg required for media probe')
 result=subprocess.run([ffmpeg,'-hide_banner','-i',str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 text=result.stderr
 duration=re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',text)
 video=next((line for line in text.splitlines() if re.search(r'Stream.*Video:',line)), '')
 size=re.search(r'(?<![\w.])(\d{2,6})x(\d{2,6})(?![\w.])',video)
 if not duration or not size:raise ValueError('Cannot probe video geometry/duration: '+str(p))
 hours,minutes,seconds=duration.groups()
 return {'streams':[{'width':int(size[1]),'height':int(size[2])}], 'format':{'duration':str(int(hours)*3600+int(minutes)*60+float(seconds))}}

def safe_copy(src,dst):
 if src.is_symlink():raise ValueError('Metadata symlink rejected')
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--processed-root',type=pathlib.Path,required=True);ap.add_argument('--metadata-root',type=pathlib.Path,required=True);ap.add_argument('--site-root',type=pathlib.Path,default=ROOT);ap.add_argument('--apply',action='store_true');ap.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));ap.add_argument('--ffprobe',default=shutil.which('ffprobe'));ap.add_argument('--task-metadata',type=pathlib.Path,help='JSON task id -> title/titleEn/instructionEn (no inferred translations)');a=ap.parse_args()
 root=a.site_root.resolve();dist=root/'dist';archive=dist/'archive';catalog=jsonp(archive/'catalog.js');site=read(dist/'data/episodes.json');existing={e['id'] for e in site['episodes']}; tasks={t['id']:t for t in site['tasks']}; taskmeta=read(a.task_metadata) if a.task_metadata else {}
 raw={}
 for p in a.metadata_root.rglob('record.json'):
  if p.parent.name in raw:raise ValueError('Duplicate metadata record_id '+p.parent.name)
  raw[p.parent.name]=p.parent
 todo=[p for p in sorted(a.processed_root.rglob('manifest.json')) if p.parent.name not in existing]
 print(json.dumps({'existing':len(existing),'candidateNew':len(todo),'newRecordIds':[p.parent.name for p in todo],'apply':a.apply}),flush=True)
 if not a.apply:return
 if not a.ffmpeg:raise ValueError('ffmpeg required (ffprobe is optional)')
 from PIL import Image
 operator=read(root/'scripts/operator-records.json');meta=read(root/'scripts/metadata-provenance.json');proof=read(root/'scripts/cache/evaluation-provenance.json');mapping=[]
 with tempfile.TemporaryDirectory(prefix='piper-batch-') as tmp:
  temp=pathlib.Path(tmp).resolve();source=temp/'source';out=temp/'out';out.mkdir()
  for mf in todo:
   rid=mf.parent.name;processed=mf.parent;task=processed.parent.parent.name;scene_num=int(''.join(c for c in processed.parent.name if c.isdigit()));case=f'piper/{task}/scene_{scene_num:03d}/{rid}';run=source/case
   if rid not in raw:raise ValueError('Missing raw metadata for '+rid)
   record=read(raw[rid]/'record.json')
   for p in raw[rid].rglob('*'):
    rel=p.relative_to(raw[rid]);allowed=rel.as_posix() in ('record.json','events.jsonl','initial_observation.json','task_manual/MANUAL.md','task_manual/manifest.json','codex/events.jsonl','codex/session.jsonl')
    if p.is_file() and allowed:safe_copy(p,run/rel)
   manifest=read(mf);images=[]
   for item in manifest['records']:
    rel=pathlib.PurePosixPath(item['output']);original=pathlib.PurePosixPath(item['source'])
    if rel.is_absolute() or '..' in rel.parts or original.is_absolute() or '..' in original.parts:raise ValueError('Unsafe manifest path')
    p=processed/rel
    if p.suffix.lower()!='.png' or sha(p)!=item['output_sha256']:raise ValueError('PNG hash mismatch '+str(rel))
    if original.parent.as_posix()=='frames':safe_copy(p,run/rel);images.append(rel.as_posix())
   events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines() if line.strip()];durations=times(events,record)
   entry,warnings=_episode(run/'record.json',run,source,out);path=out/entry['data_file'];detail=jsonp(path);entry.update(durations);detail.update(durations);entry['record_id']=detail['record_id']=rid;entry['canonical_case']=detail['canonical_case']=case
   manual=detail.get('manual') or {}
   if not manual.get('sha256'):raise ValueError('Missing real task manual '+rid)
   if not detail['steps'] or any(not s['images'] for s in detail['steps']):raise ValueError('Missing event observations '+rid)
   path.write_text('window.registerEpisode('+_json(detail)+');\n')
   video=processed/'preview.mp4';info=probe(a.ffprobe,video,a.ffmpeg);stream=info['streams'][0]
   if stream['width']!=1280 or (stream['height']!=480 and stream['height']<540):raise ValueError('Unexpected preview geometry '+rid+': '+str(stream))
   dest=dist/'media'/f'{rid}.mp4';dest.parent.mkdir(exist_ok=True)
   if stream['height']==480:shutil.copy2(video,dest)
   else:subprocess.run([a.ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(video),'-vf','crop=1280:480:0:60','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)],check=True)
   cropped=probe(a.ffprobe,dest,a.ffmpeg)
   if (cropped['streams'][0]['width'],cropped['streams'][0]['height'])!=(1280,480):raise ValueError('Crop validation failed')
   heads=sorted((run/'frames').glob('*_head_camera.png'));head=heads[len(heads)//2];right=head.with_name(head.name.replace('_head_camera','_right_camera'));poster=Image.new('RGB',(1280,480))
   for x,p in ((0,head),(640,right)):
    with Image.open(p) as im:
     if im.size!=(640,480):raise ValueError('Unexpected camera geometry')
     poster.paste(im.convert('RGB'),(x,0))
   poster.save(dist/'media'/f'{rid}.jpg',quality=92,subsampling=0)
   ev=entry.get('evaluation');confirmed=ev and ev.get('source')=='operator' and ev.get('status')=='confirmed' and type(ev.get('success')) is bool;outcome=('success' if ev['success'] else 'failure') if confirmed else 'unlabelled'
   first=next((e['time'] for e in events if e.get('event')=='start_episode' and e.get('time')),None)
   site['episodes'].append({'id':rid,'archiveId':entry['id'],'canonicalCase':case,'task':task,'scene':f'scene_{scene_num:03d}','title':f'Scene {scene_num:03d}','observations':len(detail['steps']),'video':f'media/{rid}.mp4','poster':f'media/{rid}.jpg','outcome':outcome,'outcomeLabel':{'success':'Success','failure':'Failure','unlabelled':''}[outcome],'recordedAt':stamp(first).astimezone(SHANGHAI).isoformat() if first else None,'durationSeconds':float(cropped['format']['duration'])})
   if task not in tasks:
    tm=taskmeta.get(task,{})
    tasks[task]={'id':task,'title':tm.get('title',task.replace('_',' ').title()),'titleEn':tm.get('titleEn',task.replace('_',' ').title()),'description':tm.get('description',''),'instructionEn':tm.get('instructionEn','')}
   operator.append({'case':case,'record_id':rid,'archiveId':entry['id'],'evaluation':ev or {},'summary':sanitize_public_data(record.get('summary',{}))})
   meta['cases'].append({'case':case,'evaluation':ev or {},'summary':sanitize_public_data(record.get('summary',{})),'posterFrames':[head.relative_to(source).as_posix(),right.relative_to(source).as_posix()],'videoSha256':sha(video),'manifestSha256':sha(mf)})
   proof.append({'id':entry['id'],'dataSha256':sha(path),'backend':entry['backend'],'platformName':entry['platform_name'],'task':task,'model':entry['model'],'reasoningEffort':entry['reasoning_effort'],'taskConfig':entry['task_config'],'resultSource':entry['result_source'],'archiveStatus':entry['archive_status'],'manualSha256':manual['sha256'],'manualMode':manual.get('mode'),'success':entry['success'],'operatorEvaluation':ev})
   platform=next(p for p in catalog['platforms'] if p['id']=='piper');group=next((t for t in platform['tasks'] if t['id']=='piper/'+task),None)
   if group is None:group={'id':'piper/'+task,'name':task,'backend':'piper','platform_name':'Piper','episodes':[]};platform['tasks'].append(group)
   if any(e['id']==entry['id'] for p in catalog['platforms'] for t in p['tasks'] for e in t['episodes']):raise ValueError('Archive ID collision '+rid)
   group['episodes'].append(entry);mapping.append({'record_id':rid,'archiveId':entry['id'],'canonical_case':case,'manifestSha256':sha(mf)})
  for p in catalog['platforms']:
   for t in p['tasks']:t['summary']=_summary(t['episodes'])
   p['summary']={'tasks':len(p['tasks']),**_summary([e for t in p['tasks'] for e in t['episodes']])}
  catalog['tasks']=[t for p in catalog['platforms'] for t in p['tasks']];allentries=[e for t in catalog['tasks'] for e in t['episodes']];catalog['summary']={'platforms':len(catalog['platforms']),'tasks':len(catalog['tasks']),**_summary(allentries)};catalog['generated_at']=datetime.datetime.now(SHANGHAI).isoformat()
  for p in (out/'episodes').iterdir() if (out/'episodes').exists() else []:shutil.copytree(p,archive/'episodes'/p.name,dirs_exist_ok=True)
  (archive/'catalog.js').write_text('window.EVALUATION_CATALOG = '+_json(catalog)+';\n');shutil.copy2(archive/'catalog.js',root/'scripts/cache/catalog.js')
 for task_id,tm in taskmeta.items():
  if task_id in tasks and 'instructionEn' in tm:tasks[task_id]['instructionEn']=tm['instructionEn']
 site['tasks']=list(tasks.values());site['site'].update(updatedAt=datetime.datetime.now(SHANGHAI).date().isoformat(),videoZip='downloads/piper-videos.zip',episodeCount=len(site['episodes']),taskCount=len(tasks),realWorldAvailableTaskCount=len(tasks),observationCount=sum(e['observations'] for e in site['episodes']))
 # imageCount includes only actual published episode camera frames (manual images excluded).
 site['site']['imageCount']=sum(len(list(((archive/e['data_file']).parent/'frames').glob('*.png'))) for p in catalog['platforms'] if p['id']=='piper' for t in p['tasks'] for e in t['episodes'])
 meta['verifiedAt']=datetime.datetime.now(SHANGHAI).date().isoformat()
 write(dist/'data/episodes.json',site);write(root/'scripts/operator-records.json',operator);write(root/'scripts/metadata-provenance.json',meta);write(root/'scripts/cache/evaluation-provenance.json',sorted(proof,key=lambda x:x['id']))
 manifest=read(root/'scripts/cache/cache-manifest.json');manifest['sha256']={k:sha(root/'scripts/cache'/k) for k in manifest['sha256']};write(root/'scripts/cache/cache-manifest.json',manifest)
 mapfile=root/'scripts/piper-batch-imports.json';old=read(mapfile) if mapfile.exists() else [];write(mapfile,old+mapping)
 print(json.dumps({'added':len(mapping),'totalReal':len(site['episodes']),'totalArchive':len(allentries)}))
if __name__=='__main__':main()
