"""Post-draw comparison using frozen pre-target weights and a target-free database."""
from pathlib import Path
import sys,json,hashlib,datetime
import torch
sys.path.insert(0,str(Path.cwd()))
from backend.src import db
from backend.src.config import MODELS,MODEL_LABELS
from backend.src.models import get_model,lstm_model,transformer_model,xgboost_model
from backend.src.tasks.dataio import load_history
from backend.src.utils.numbers import encode,decode,count_hits
from backend.src.utils.prizes import prize_for_hits,previous_pool
root=Path(sys.argv[1]);frozen=root/'frozen';db.DB_PATH=frozen/'daletou.db'
torch.set_num_threads(2);torch.set_num_interop_threads(1)
for module,name in [(lstm_model,'lstm'),(transformer_model,'transformer')]:
 module.CKPT_PATH=frozen/f'{name}_state.pt';module.META_PATH=frozen/f'{name}_meta.json'
 assert json.loads(module.META_PATH.read_text())['last_trained_issue']=='26117'
xgboost_model.CACHE_PATH=frozen/'xgboost_probs.npz'
history=load_history();assert str(history.iloc[-1].issue)=='26117' and len(history)==2935
before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in frozen.iterdir() if f.suffix in ('.pt','.npz')}
original={r['model']:r for r in json.loads((root/'original.json').read_text())};models=[]
for name in MODELS:
 model=get_model(name,**({'target_issue':'26118'} if name=='ensemble' else {}));ticket=model.predict(history,n=1)[0]
 with db.get_conn() as conn:
  conn.execute('INSERT INTO predictions(issue,model,ticket_idx,front,back) VALUES(?,?,?,?,?)',('26118',name,0,encode(ticket.front),encode(ticket.back)));conn.commit()
 models.append(dict(model=name,label=MODEL_LABELS[name],original=dict(front=decode(original[name]['front']),back=decode(original[name]['back']),created_at=original[name]['created_at']),retrained=dict(front=sorted(ticket.front),back=sorted(ticket.back))))
 print(name,encode(ticket.front),encode(ticket.back),flush=True)
# Outcomes are loaded only after all tickets have been generated and frozen.
import sqlite3
real=sqlite3.connect('file:data/daletou.db?mode=ro',uri=True).execute("SELECT draw_date,front,back FROM draws WHERE issue='26118'").fetchone()
with db.get_conn() as conn:pool=previous_pool(conn,'26118')
for m in models:
 for key in ['original','retrained']:
  t=m[key];f,b=count_hits(t['front'],t['back'],decode(real[1]),decode(real[2]));level,amount=prize_for_hits('26118',f,b,pool)
  t['result']=dict(front_hit=f,back_hit=b,level=level,amount=amount,won=level is not None)
 m['changed']=any(m['original'][k]!=m['retrained'][k] for k in ['front','back'])
for name,sha in before.items():assert hashlib.sha256((frozen/name).read_bytes()).hexdigest()==sha,name
report=dict(issue='26118',kind='retrospective_comparison',generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),trained_through_issue='26117',history_rows=2935,money_feature_version=2,real=dict(date=real[0],front=decode(real[1]),back=decode(real[2])),models=models,summary={key:dict(tickets=9,cost=18,winning_tickets=sum(m[key]['result']['won'] for m in models),estimated_prize=sum(m[key]['result']['amount'] for m in models)) for key in ['original','retrained']},weights_sha256=before,predictions_replaced=False,methodology='事后对照：仅使用26117及以前开奖、核对结果和原先已保存的重训权重，全部选号完成后才读取26118结果。不计入提前发布成绩；奖金为规则估算。')
(root/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(report['summary'],flush=True)
