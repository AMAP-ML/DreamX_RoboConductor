#!/usr/bin/env python3
"""Build public assets exclusively from redacted PNGs and preview MP4s.
Requires Pillow. Operator record snapshot is optional; absent evidence stays unlabelled.
"""
import argparse, collections, datetime, hashlib, json, pathlib, shutil, struct, zipfile, subprocess, sys, urllib.request, io
import os
from PIL import Image

def read_json(path):
    return json.loads(path.read_text())

def duration(path):
    # Read ISO BMFF movie header; no ffmpeg dependency or timing inference.
    data = path.read_bytes()
    def atoms(start,end):
        while start+8 <= end:
            size, kind = struct.unpack('>I4s',data[start:start+8]); header=8
            if size == 1:
                size=struct.unpack('>Q',data[start+8:start+16])[0]; header=16
            if size == 0: size=end-start
            if size<header: raise ValueError('Invalid MP4 atom')
            yield kind,start+header,start+size
            start+=size
    for kind,start,end in atoms(0,len(data)):
        if kind==b'moov':
            for sub,a,b in atoms(start,end):
                if sub==b'mvhd':
                    offset=a+(20 if data[a]==1 else 12)
                    scale=struct.unpack('>I',data[offset:offset+4])[0]
                    fmt='>Q' if data[a]==1 else '>I'; width=8 if data[a]==1 else 4
                    ticks=struct.unpack(fmt,data[offset+4:offset+4+width])[0]
                    return round(ticks/scale,3)
    raise ValueError(f'Missing movie header: {path}')

def build_hero(out, ffmpeg):
    """Join two real six-second excerpts; keep both complete camera views."""
    episodes=read_json(out/'data'/'episodes.json')['episodes']
    chosen=[next(e for e in episodes if e['task']==task and e['outcome']=='success') for task in ('put_pen','put_phone')]
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y']
    for e in chosen:
        cmd+=['-ss',str(int(e['durationSeconds']*0.2*2)/2),'-t','6','-i',str(out/e['video'])]
    cmd+=['-filter_complex','[0:v]crop=1280:480:0:ih-480,setpts=PTS-STARTPTS[a];[1:v]crop=1280:480:0:ih-480,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,setpts=N/(2*TB)[v]',
          '-map','[v]','-r','2','-an','-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'media'/'hero.mp4')]
    subprocess.run(cmd,check=True)
    # Pillow gives an explicit JPEG quality matching episode posters.
    import io
    frame=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-ss','8','-i',str(out/'media'/'hero.mp4'),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],check=True,stdout=subprocess.PIPE).stdout
    Image.open(io.BytesIO(frame)).convert('RGB').save(out/'media'/'hero.jpg',quality=92,subsampling=0)
    assert duration(out/'media'/'hero.mp4')==12
    print(json.dumps({'heroSeconds':12,'sourceEpisodes':[e['id'] for e in chosen],'crop':'1280x480 at y=60','excerptStartFraction':0.2}))

def crop_video(source, target, ffmpeg):
    if not ffmpeg: raise ValueError('FFmpeg is required for public video crops')
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(source),'-vf','crop=1280:480:0:60','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)

def video_zip(out,cases):
    with zipfile.ZipFile(out/'downloads'/'piper-10-videos.zip','w',compression=zipfile.ZIP_STORED) as z:
        for c in cases:
            rid=c['record_id'];z.write(out/'media'/f'{rid}.mp4',f'{rid}.mp4')

def build_simulation(out, ffmpeg):
    if not ffmpeg: raise ValueError('FFmpeg required')
    summary=read_json(pathlib.Path(__file__).parent/'simulation-summary.json')
    selected=[('adjust_bottle','Adjust the Bottle'),('beat_block_hammer','Hammer the Block'),('open_microwave','Open the Microwave'),('handover_mic','Pass the Microphone'),('hanging_mug','Hang the Mug'),('stack_blocks_three','Stack Three Blocks')]
    featured=[];cache=pathlib.Path(__file__).parent/'simulation-frames';base=os.environ.get('SHOWCASE_VIEWER_BASE', 'http://127.0.0.1:18080/').rstrip('/')+'/'
    catalog_raw=urllib.request.urlopen(base+'catalog.js',timeout=30).read().decode()
    catalog=json.loads(catalog_raw.split('=',1)[1].strip().rstrip(';'))
    entries={ep['id']:ep for group in catalog['tasks'] for ep in group['episodes']}
    for task,title in selected:
        row=next(r for r in summary['records'] if r['task']==task and r['outcome']=='success')
        rid=row['id']; folder=cache/rid;folder.mkdir(parents=True,exist_ok=True)
        raw=urllib.request.urlopen(base+entries[rid]['data_file'],timeout=30).read().decode()
        detail=json.loads(raw[raw.index('(')+1:raw.rfind(')')])
        assert detail['success'] is True and detail['counted'] is True and detail['result_source']=='official'
        # Numeric observation number from stored image name; never filesystem iteration order.
        steps=[s for s in detail['steps'] if all(c in s.get('images',{}) for c in ('head_camera','left_camera','right_camera'))]
        steps.sort(key=lambda s:int(pathlib.Path(s['images']['head_camera']).name.split('_')[0]))
        frames=[]
        for step in steps:
            images={}
            for camera in ('head_camera','left_camera','right_camera'):
                rel=step['images'][camera];local=folder/pathlib.Path(rel).name
                if not local.exists(): local.write_bytes(urllib.request.urlopen(base+rel,timeout=30).read())
                with Image.open(local) as image: images[camera]=image.convert('RGB').copy()
            frame=Image.new('RGB',(960,480))
            frame.paste(images['head_camera'].resize((640,480),Image.Resampling.LANCZOS),(0,0))
            for y,camera in ((0,'left_camera'),(240,'right_camera')):
                frame.paste(images[camera].resize((320,240),Image.Resampling.LANCZOS),(640,y))
            frames.append(frame)
        assert frames
        name=f'sim-{task}';target=out/'media'/f'{name}.mp4'
        proc=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','960x480','-r','2','-i','-','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],stdin=subprocess.PIPE)
        for frame in frames: proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait():raise RuntimeError('Simulation encoding failed')
        frames[len(frames)//2].save(out/'media'/f'{name}.jpg',quality=92,subsampling=0)
        featured.append({'id':rid,'task':task,'title':title,'video':f'media/{name}.mp4','poster':f'media/{name}.jpg'})
        print(json.dumps({'task':task,'frames':len(frames),'durationSeconds':duration(target)}),flush=True)
    (out/'data'/'simulation-featured.json').write_text(json.dumps(featured,ensure_ascii=False,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--processed-root',type=pathlib.Path,required=True)
    p.add_argument('--records-json',type=pathlib.Path)
    p.add_argument('--out',type=pathlib.Path,default=pathlib.Path('dist'))
    p.add_argument('--media-only',action='store_true',help='Only recrop redacted Piper videos and rebuild their ZIP')
    p.add_argument('--simulation',action='store_true',help='Build six official successful simulation examples only')
    p.add_argument('--hero',action='store_true',help='Also build a 12-second hero from two successful redacted episodes')
    p.add_argument('--hero-only',action='store_true',help='Only build hero; preserve existing case assets and metadata')
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'),help='FFmpeg executable required for hero')
    a=p.parse_args(); root=a.processed_root.resolve(); out=a.out.resolve()
    if not a.ffmpeg:
        sys.path.insert(0,str(pathlib.Path.cwd()/'work/video_export_deps'))
        try:
            import imageio_ffmpeg
            a.ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError: pass
    if a.simulation:
        build_simulation(out,a.ffmpeg); return
    if a.media_only:
        if not a.ffmpeg: p.error('--ffmpeg required to crop public videos')
        cases=read_json(root.parent/'case-list.json')
        for c in cases: crop_video(root/c['case']/'preview.mp4',out/'media'/f"{c['record_id']}.mp4",a.ffmpeg)
        video_zip(out,cases); return
    if a.hero_only:
        if not a.ffmpeg: p.error('--ffmpeg is required for hero')
        build_hero(out,a.ffmpeg); return
    cases=read_json(root.parent/'case-list.json'); batch=read_json(root/'batch_summary.json')
    records={r['case']:r for r in read_json(a.records_json)} if a.records_json else {}
    tasks=[{'id':'put_pen','title':'把笔放入笔筒','titleEn':'Place the pen in the holder','description':'Piper 单臂真机将笔放入笔筒。'}, {'id':'put_phone','title':'把手机放上支架','titleEn':'Place the phone on the stand','description':'Piper 单臂真机将手机放到支架上。'}]
    titles={t['id']:t['title'] for t in tasks}
    for folder in ('media','data','downloads'): (out/folder).mkdir(parents=True,exist_ok=True)
    episodes=[]; provenance=[]
    for c in cases:
        case=c['case']; src=root/case; rid=c['record_id']; scene=case.split('/')[2]
        frames=sorted((src/'frames').glob('*_head_camera.png'))
        assert len(frames)==c['observations']
        # Middle observation shows the episode in progress; both cameras retain full resolution.
        head=frames[len(frames)//2]; right=head.with_name(head.name.replace('_head_camera','_right_camera'))
        poster=Image.new('RGB',(1280,480))
        for x,image in ((0,head),(640,right)):
            with Image.open(image) as im:
                assert im.size==(640,480)
                poster.paste(im.convert('RGB'),(x,0))
        poster.save(out/'media'/f'{rid}.jpg',quality=92,subsampling=0)
        video=src/'preview.mp4'; crop_video(video,out/'media'/f'{rid}.mp4',a.ffmpeg)
        ev=records.get(case,{}).get('evaluation',{})
        confirmed=ev.get('status')=='confirmed' and ev.get('source')=='operator' and type(ev.get('success')) is bool
        outcome=('success' if ev['success'] else 'failure') if confirmed else 'unlabelled'
        stamp=rid.split('-')[2:4]; recorded=datetime.datetime.strptime(''.join(stamp),'%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).isoformat()
        episodes.append({'id':rid,'task':c['task'],'scene':scene,'title':f"{titles[c['task']]} · {scene}",'observations':c['observations'],'video':f'media/{rid}.mp4','poster':f'media/{rid}.jpg','outcome':outcome,'outcomeLabel':{'success':'成功','failure':'失败','unlabelled':'未标注'}[outcome],'recordedAt':recorded,'durationSeconds':duration(video)})
        provenance.append({'case':case,'evaluation':ev,'summary':records.get(case,{}).get('summary',{}),'posterFrames':[str(head.relative_to(root)),str(right.relative_to(root))],'videoSha256':hashlib.sha256(video.read_bytes()).hexdigest()})
    # ZIP is rebuilt from the exact public, already-redacted video assets.
    with zipfile.ZipFile(out/'downloads'/'piper-10-videos.zip','w',compression=zipfile.ZIP_STORED) as z:
        for e in episodes: z.write(out/e['video'],f"{e['id']}.mp4")
    payload={'site':{'title':'RoboConductor · Piper 真机评测','description':'10 段 Piper 真机评测记录，双视角脱敏观测以 2 fps 播放，非实时录像；结果来自操作员确认。','updatedAt':'2026-10-22','episodeCount':len(episodes),'taskCount':len(tasks),'observationCount':sum(e['observations'] for e in episodes),'imageCount':batch['images'],'videoZip':'downloads/piper-10-videos.zip','sourceZip':'downloads/piper-showcase-source.zip'},'tasks':tasks,'episodes':episodes}
    (out/'data'/'episodes.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    (pathlib.Path(__file__).parent/'metadata-provenance.json').write_text(json.dumps({'verifiedAt':'2026-10-22','recordSource':'evaluation_records operator evidence snapshot','recordsSnapshotProvided':bool(a.records_json),'playback':'preview.mp4, observation slideshow at 2 fps, not real-time','cases':provenance},ensure_ascii=False,indent=2)+'\n')
    assert len(episodes)==10
    for e in episodes:
        assert (out/e['video']).is_file() and (out/e['poster']).is_file()
    print(json.dumps({'episodes':len(episodes),'outcomes':dict(collections.Counter(e['outcome'] for e in episodes)),'observations':payload['site']['observationCount'],'images':payload['site']['imageCount']},ensure_ascii=False))
    if a.hero:
        if not a.ffmpeg: p.error('--ffmpeg is required for hero')
        build_hero(out,a.ffmpeg)
if __name__=='__main__': main()
