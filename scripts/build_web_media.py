#!/usr/bin/env python3
"""Create lightweight playback assets; original videos and downloads stay intact."""
import argparse, hashlib, json, re, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def refresh_aliases(dist, previous, assets):
    registry = dist / 'data/media-aliases.json'
    aliases = json.loads(registry.read_text())['aliases'] if registry.exists() else {}
    for source, old in previous.items():
        for variant in ('src', 'thumbnail'):
            name = old.get(variant)
            if name and name.startswith('media/web/') and name != assets[source].get(variant):
                aliases[name] = {'source': source, 'variant': variant}
    for name, reference in aliases.items():
        assert name.startswith('media/web/') and '..' not in Path(name).parts
        current = assets[reference['source']][reference['variant']]
        assert current.startswith('media/') and '..' not in Path(current).parts
        if current != name:
            shutil.copyfile(dist / current, dist / name)
    registry.write_text(json.dumps({'aliases': aliases}, indent=1) + '\n')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--ffmpeg',required=True);ap.add_argument('--workers',type=int,default=3);a=ap.parse_args()
    data=json.loads((DIST/'data/episodes.json').read_text())
    episodes=data['episodes']+json.loads((DIST/'data/simulation-featured.json').read_text())
    output=DIST/'media/web';output.mkdir(exist_ok=True)
    previous = json.loads((DIST/'data/web-media.json').read_text())['assets'] if (DIST/'data/web-media.json').exists() else {}
    def encode(item):
        source=DIST/item['video']; fingerprint=digest(source); stem=source.stem+'-'+fingerprint[:10]
        target=output/(stem+'.mp4')
        if not target.exists():
            subprocess.run([a.ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(source),'-vf','scale=min(960\\,iw):-2:flags=lanczos','-an','-c:v','libx264','-threads','2','-preset','slow','-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)
        # Keep the source when an already small clip cannot benefit from re-encoding.
        playback=target if target.stat().st_size<source.stat().st_size else source
        poster=DIST/item['poster']; image_stem=poster.stem+'-'+digest(poster)[:10]
        cover=output/(image_stem+'.webp'); thumb=output/(image_stem+'-thumb.webp')
        for dest,width,quality in ((cover,960,85),(thumb,240,80)):
            if not dest.exists():
                with Image.open(poster) as im:
                    im=im.convert('RGB');im.thumbnail((width,width),Image.Resampling.LANCZOS);im.save(dest,'WEBP',quality=quality,method=6)
        return {item['video']:{'src':playback.relative_to(DIST).as_posix(),'sourceBytes':source.stat().st_size,'bytes':playback.stat().st_size,'sourceSha256':fingerprint},item['poster']:{'src':cover.relative_to(DIST).as_posix(),'thumbnail':thumb.relative_to(DIST).as_posix(),'sourceBytes':poster.stat().st_size,'bytes':cover.stat().st_size}}
    assets={}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for result in pool.map(encode,episodes):assets.update(result)
    refresh_aliases(DIST, previous, assets)
    (DIST/'data/web-media.json').write_text(json.dumps({'assets':assets},indent=1)+'\n')
    html=DIST/'index.html';text=html.read_text()
    # Poster images are fetched by the browser before the app initializes.
    by_id={item['id']:item for item in episodes}
    def hero(match):
        tag=match[0];record=re.search(r'data-hero-episode="([^"]+)"',tag)
        item=by_id[record[1]]
        tag=re.sub(r' poster="[^"]*"', ' poster="'+assets[item['poster']]['src']+'"',tag)
        return re.sub(r' src="[^"]*"','',tag)
    text=re.sub(r'<video\b[^>]*data-hero-episode="[^"]+"[^>]*>',hero,text)
    html.write_text(text)
    print(json.dumps({'videos':len(episodes),'originalVideoBytes':sum(v['sourceBytes'] for k,v in assets.items() if k.endswith('.mp4')),'webVideoBytes':sum(v['bytes'] for k,v in assets.items() if k.endswith('.mp4')),'originalPosterBytes':sum(v['sourceBytes'] for k,v in assets.items() if not k.endswith('.mp4')),'webPosterBytes':sum(v['bytes'] for k,v in assets.items() if not k.endswith('.mp4'))}))
if __name__=='__main__':main()
