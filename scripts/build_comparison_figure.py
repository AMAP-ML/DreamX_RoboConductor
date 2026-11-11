#!/usr/bin/env python3
"""Render the method-comparison dataset as desktop and mobile figures."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
from matplotlib.transforms import blended_transform_factory

ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'dist/data/method-comparison.json').read_text())
ROWS=sorted(DATA['entries'],key=lambda r:r['successRate'],reverse=True)
assert len(ROWS)==19 and ROWS[0]['id']=='roboconductor'
assert DATA['axis']==[0,100] and all(0<=r['successRate']<=100 for r in ROWS)
DELTA=round(ROWS[0]['successRate']-ROWS[1]['successRate'],2)
OUT=ROOT/'dist/media/comparison';OUT.mkdir(parents=True,exist_ok=True)
PAPER='#f7f5ef';INK='#203b32';MUTED='#64756c';GREEN='#174f43';TRACK='#e8ebe2'
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'path','svg.hashsalt':'roboconductor-c2r-table3','savefig.facecolor':PAPER})

def chart(mobile=False):
    fig=plt.figure(figsize=(4.6,15.3) if mobile else (14,10.5),facecolor=PAPER)
    ax=fig.add_axes([.065,.105,.87,.80] if mobile else [.355,.105,.585,.755])
    ax.set_facecolor('none');ax.set_xlim(0,100);ax.set_ylim(len(ROWS)-.35,-.8)
    ax.set_xticks([0,20,40,60,80,100]);ax.set_yticks([])
    ax.tick_params(axis='x',labelsize=9.5 if mobile else 10.5,colors=MUTED,length=0,pad=10)
    for spine in ax.spines.values():spine.set_visible(False)
    trans=blended_transform_factory(ax.transAxes if mobile else fig.transFigure,ax.transData)
    rect=Rectangle((0 if mobile else .022,-.60),1 if mobile else .957,1.18 if mobile else 1.02,transform=trans,facecolor='#e1eee7',edgecolor='none',clip_on=False,zorder=0)
    ax.add_patch(rect)
    if not mobile:ax.grid(axis='x',color='#d9dfd6',linewidth=.7,zorder=0)
    for y,row in enumerate(ROWS):
        color=DATA['groups'][row['group']]['color'];ours=row['id']=='roboconductor'
        center=y+.31 if mobile else y
        ax.barh(center,100,height=.23 if mobile else .44,color=TRACK,edgecolor='none',zorder=1)
        ax.barh(center,row['successRate'],height=.23 if mobile else .44,color=color,edgecolor='none',zorder=2)
        name=row['method']
        if mobile and ours:name='DreamX-RoboConductor'
        ax.text(0 if mobile else .035,y-.30 if mobile else y-.13,name,transform=trans,va='center',ha='left',fontsize=11.2 if mobile else 12.8,fontweight='bold' if ours else 'normal',color=GREEN if ours else INK)
        context=row['context']
        if mobile and ours:context='Codex · '+context
        ax.text(0 if mobile else .035,y-.015 if mobile else y+.27,context,transform=trans,va='center',ha='left',fontsize=8.3 if mobile else 9.8,color=GREEN if ours else MUTED)
        ax.text(1 if mobile else .977,y-.30 if mobile else y-.02,f"{row['successRate']:.{row.get('displayPrecision', 1)}f}",transform=trans,ha='right',va='center',fontsize=12.5 if mobile else 14.2,fontweight='bold' if ours else 'normal',color=GREEN if ours else INK)
    if mobile:
        fig.text(.06,.972,'RoboTwin 2.0 C2R',fontfamily='DejaVu Serif',fontsize=18,fontweight='bold',color=INK)
        ax.set_xlabel('Success rate (%)',fontsize=9.2,color=MUTED,labelpad=13)
    else:
        fig.text(.035,.960,'RoboTwin 2.0 C2R',fontfamily='DejaVu Serif',fontsize=24,fontweight='bold',color=INK)
        fig.text(.035,.886,'METHOD / TASK CONTEXT',fontsize=9.5,fontweight='bold',color=MUTED)
        fig.text(.355,.886,'SUCCESS RATE (%)',fontsize=9.5,fontweight='bold',color=MUTED)
        fig.text(.977,.886,'SR (%)',ha='right',fontsize=9.5,fontweight='bold',color=MUTED)
    handles=[Patch(facecolor=g['color'],label=g['label']) for g in DATA['groups'].values()]
    if mobile:
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.045,.063),ncol=2,frameon=False,fontsize=6.8,handlelength=1.1,columnspacing=1.0,labelspacing=.8)
    else:
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.028,.062),ncol=3,frameon=False,fontsize=10,handlelength=1.2,columnspacing=2.2,labelspacing=.8)
    stem='c2r-comparison-mobile' if mobile else 'c2r-comparison'
    fig.savefig(OUT/(stem+'.svg'),bbox_inches='tight',pad_inches=.16,metadata={'Date':None,'Creator':'DreamX-RoboConductor'})
    svg=OUT/(stem+'.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    fig.savefig(OUT/(stem+'.png'),dpi=180,bbox_inches='tight',pad_inches=.16)
    plt.close(fig)
chart();chart(True)
print(json.dumps({'settings':len(ROWS),'highest':ROWS[0]['successRate'],'lead_percentage_points':DELTA,'axis':DATA['axis']}))
