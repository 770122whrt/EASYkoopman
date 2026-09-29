"""Actual trajectories, including partial failures; no synthetic confidence bands."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
        'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'lines.linewidth':1.5,
        'pdf.fonttype':42,'ps.fonttype':42,'savefig.bbox':'tight'})
    fig,axes=plt.subplots(3,4,figsize=(12,7.2),sharex=True,squeeze=False)
    arms=[('feedback','Feedback PD + feedforward','#555555','-'),
          ('projected_koopman','Projected Koopman-MPC','#0072B2','-'),
          ('nominal_physics','Nominal physics-MPC','#D55E00','--')]
    provenance={};handles={}
    for col,cfg in enumerate(('base','uuv4','long_body','uuv6')):
        axes[0,col].set_title(cfg,weight='bold');axes[0,col].axhline(.04,color='#999999',ls=':',lw=1)
        axes[1,col].axhline(0,color='#999999',ls=':',lw=1)
        missing=[];stopped_count=0
        for kind,label,color,style in arms:
            suffix='r1' if cfg=='base' and kind=='feedback' else 'r3'
            directory=a.root/(cfg+'-pitch-'+kind+'-'+suffix);path=directory/'trace.json.gz'
            if not path.exists():missing.append(kind);continue
            raw=path.read_bytes();d=json.loads(gzip.decompress(raw));rows=d.get('substeps',[])
            digest=hashlib.sha256(raw).hexdigest();accepted=(directory/'acceptance.json').exists()
            if accepted and json.loads((directory/'acceptance.json').read_text())['trace_sha256']!=digest:
                raise ValueError('plot_evidence_hash')
            provenance[directory.name]=dict(sha256=digest,accepted=accepted,physics_steps=len(rows))
            if not rows:missing.append(kind+' (failed before physics)');continue
            x=np.asarray([r['state_after_physics_11'][0] for r in rows]);q=x[:,1:5]
            q=q/np.linalg.norm(q,axis=1,keepdims=True)
            pitch=np.arcsin(np.clip(2*(q[:,0]*q[:,2]-q[:,3]*q[:,1]),-1,1))
            controls=np.asarray([r['command']['telemetry']['virtual_control_4'][0] for r in rows])
            t=np.arange(1,len(rows)+1)/120
            for r,(ax,values) in enumerate(zip(axes[:,col],(pitch,100*(x[:,0]-5.5),controls[:,1]))):
                if r==2:
                    line,=ax.step(np.r_[0,t],np.r_[values,values[-1]],where='post',color=color,ls=style,label=label)
                else:line,=ax.plot(t,values,color=color,ls=style,label=label)
                handles[label]=line
                if not accepted:ax.plot(t[-1],values[-1],marker='x',color=color,ms=7)
            if not accepted:
                axes[0,col].text(.02,.92-.1*stopped_count,f'{kind}: stopped',transform=axes[0,col].transAxes,fontsize=6,color=color)
                stopped_count+=1
        if missing:axes[0,col].text(.02,.03,'Missing: '+', '.join(missing),transform=axes[0,col].transAxes,fontsize=6,wrap=True)
        axes[2,col].set_xlabel('Simulation time (s)');axes[2,col].set_xlim(0,2)
    for ax,label in zip(axes[:,0],('Pitch (rad)','Depth error (cm)','Pitch command')):ax.set_ylabel(label)
    fig.legend(handles.values(),handles.keys(),loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,-.01))
    fig.suptitle('Continuous MPC development comparison: same task and constraints, one episode per arm\n2 s simulation-time control; not a real-time or statistical generalization claim',fontsize=11)
    fig.tight_layout(rect=(0,.045,1,.93))
    fig.savefig(a.output/'continuous-v76-trajectories.pdf');fig.savefig(a.output/'continuous-v76-trajectories.png',dpi=300)
    (a.output/'figure-sources.json').write_text(json.dumps(provenance,indent=2))


if __name__=='__main__':main()
