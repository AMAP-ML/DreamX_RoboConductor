#!/usr/bin/env python3
"""Merge verified aggregate results and local demonstration assets."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'dist/data/episodes.json';data=json.loads(p.read_text());sim=json.loads((root/'scripts/simulation-summary.json').read_text())
data['site'].update(title='RoboConductor',description='Language-guided robotics in simulation and the real world.',realWorldTaskCount=10,realWorldAvailableTaskCount=len(data['tasks']),simulationZip='downloads/simulation-highlights.zip')
for task in data['tasks']:
 task['title']=task['titleEn'];task['description']=task['titleEn']+'.'
for ep in data['episodes']:
 ep['title']='Scene '+ep['scene'].split('_')[-1];ep['outcomeLabel']={'success':'Success','failure':'Failure','unlabelled':''}[ep['outcome']]
data['simulation']={'taskCount':sim['taskCount'],'episodes':sim['caseCount'],'scoredEpisodes':sim['scoredDenominator'],'successes':sim['success'],'failures':sim['failure'],'unscored':sim['unscored'],'successRate':sim['successRate'],'tasks':[{'id':k,'name':k.replace('_',' ').title().replace('Rgb','RGB'),'episodes':v['cases'],'successes':v['success'],'failures':v['failure'],'successRate':v['success']/(v['success']+v['failure']) if v['success']+v['failure'] else None} for k,v in sim['tasks'].items()],'featured':json.loads((root/'dist/data/simulation-featured.json').read_text())}
p.write_text(json.dumps(data,indent=2)+'\n');print('Merged simulation and real-world results.')
