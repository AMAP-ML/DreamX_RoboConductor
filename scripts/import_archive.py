#!/usr/bin/env python3
"""Import catalog data and simulation frames; never import original Piper images."""
import argparse
import pathlib
import subprocess
import tarfile

REMOTE = r'''
import json,os,sys,tarfile
root=__REMOTE_ROOT__
catalog=json.loads(open(root+'/catalog.js').read().split('=',1)[1].strip().rstrip(';'))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 archive.add(root+'/catalog.js',arcname='catalog.js',recursive=False)
 for platform in catalog['platforms']:
  for task in platform['tasks']:
   for episode in task['episodes']:
    path=episode['data_file']
    archive.add(root+'/'+path,arcname=path,recursive=False)
    if platform['kind']=='simulation':
     frames=path.rsplit('/',1)[0]+'/frames'
     archive.add(root+'/'+frames,arcname=frames)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]/'dist/archive')
    parser.add_argument('--ssh-host', required=True, help='Authorized SSH host or user-configured alias')
    parser.add_argument('--remote-root', required=True, help='Remote static archive directory')
    parser.add_argument('--socket', help='Optional existing SSH control socket')
    args=parser.parse_args()
    args.destination.mkdir(parents=True,exist_ok=True)
    if args.ssh_host.startswith('-'):
        parser.error('--ssh-host must be a host, not an SSH option')
    command=['ssh','-o','BatchMode=yes']
    if args.socket:
        command.extend(['-S', args.socket])
    command.extend([args.ssh_host, 'python3 -'])
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    process.stdin.write(REMOTE.replace('__REMOTE_ROOT__', repr(args.remote_root)).encode());process.stdin.close()
    count=0;total=0
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        for member in archive:
            relative=pathlib.PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts or member.issym() or member.islnk():
                raise RuntimeError('Unsafe archive member')
            if not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsupported archive member')
            archive.extract(member,args.destination)
            if member.isfile():
                count+=1;total+=member.size
                if count%5000==0:print(f'Imported {count} files / {total} bytes',flush=True)
    if process.wait()!=0:raise RuntimeError('SSH import failed')
    print(f'Complete: {count} files / {total} bytes',flush=True)

if __name__=='__main__':main()
