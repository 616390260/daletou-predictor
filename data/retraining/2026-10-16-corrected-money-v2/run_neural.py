"""Operational retraining audit; existing model architecture and epochs are unchanged."""
import sys,json,time,hashlib,random
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path.cwd()))
import torch
from backend.src.models import lstm_model as lm, transformer_model as tm
from backend.src.config import MONEY_FEATURE_VERSION

root=Path(sys.argv[1]); history=pd.read_pickle(root/'history.pkl'); source=json.loads((root/'input.json').read_text())
torch.set_num_threads(2);torch.set_num_interop_threads(1)
train=history.iloc[:-60].copy(); test=history.iloc[-60:]
y=np.stack([lm._to_multihot(r.front,r.back) for r in test.itertuples(index=False)])

def seed():
 random.seed(source['seed']);np.random.seed(source['seed']);torch.manual_seed(source['seed'])

def metrics(p):
 p=np.clip(np.asarray(p,dtype=np.float64),1e-7,1-1e-7)
 return dict(log_loss=float(-(y*np.log(p)+(1-y)*np.log1p(-p)).mean()),brier=float(((p-y)**2).mean()))

uniform=np.tile(np.r_[np.full(35,5/35),np.full(12,2/12)],(60,1))
frequency=np.tile(np.stack([lm._to_multihot(r.front,r.back) for r in train.itertuples(index=False)]).mean(axis=0),(60,1))
results={'split':dict(train_cutoff=source['train_cutoff'],validation_first=str(test.iloc[0].issue),validation_last=str(test.iloc[-1].issue),validation_periods=60,weight_updates_during_validation=False,normalization='production pre-target history only'), 'baselines':{'uniform':metrics(uniform),'train_frequency':metrics(frequency)},'models':{}}
for name,module in [('lstm',lm),('transformer',tm)]:
 start=time.time();seed()
 print(f'[{name}] chronological validation: train through {source["train_cutoff"]}, evaluate 60 later draws',flush=True)
 if name=='lstm':
  trainer=lm.LSTMModel(); network,loss=trainer._train_full(train)
 else:
  network=tm.LotteryTransformer();X,targets=tm._prepare_tensors(train)
  loss=tm._train_epochs(network,X,targets,torch.device('cpu'),tm.EPOCHS_FULL,tm.LR_FULL,'validation-train')
 network.eval(); preds=[]
 for i in range(len(train),len(history)):
  past=history.iloc[:i]
  sales_max,pool_max=lm._sales_pool_norms(past)
  seq=np.stack([lm._build_input_vector(r,sales_max,pool_max) for r in past.tail(lm.WINDOW).itertuples(index=False)])
  with torch.no_grad():preds.append(network(torch.tensor(seq[None,...],dtype=torch.float32)).numpy()[0])
 p=np.stack(preds); assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
 np.savez(root/f'{name}_validation.npz',issues=np.array(source['validation_issues']),probabilities=p,labels=y)
 validation=dict(**metrics(p),training_loss=float(loss),epochs=module.EPOCHS_FULL)
 print(name,'validation',validation,flush=True)
 del network;seed()
 module.CKPT_PATH=root/'staged'/f'{name}_state.pt';module.META_PATH=root/'staged'/f'{name}_meta.json'
 model=lm.LSTMModel() if name=='lstm' else tm.TransformerModel()
 model._ensure_model(history)
 front,back=model._predict_probs(history)
 prediction=np.r_[front,back]
 assert prediction.shape==(47,) and np.isfinite(prediction).all() and ((prediction>=0)&(prediction<=1)).all()
 np.savez(root/f'{name}_next_probabilities.npz',front_p=front,back_p=back)
 meta=json.loads(module.META_PATH.read_text())
 meta.update(training_data_sha256=source['data_sha256'],training_rows=len(history),supervised_examples=len(history)-module.WINDOW,seed=source['seed'],full_epochs=module.EPOCHS_FULL,retrained_at=pd.Timestamp.now(tz='UTC').isoformat(),source='corrected_sales_pool_full_retrain')
 module.META_PATH.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
 assert meta['money_feature_version']==MONEY_FEATURE_VERSION and meta['last_trained_issue']==source['last_issue']
 results['models'][name]=dict(validation=validation,full_training=meta,duration_seconds=round(time.time()-start,2),checkpoint_sha256=hashlib.sha256(module.CKPT_PATH.read_bytes()).hexdigest())
 (root/'neural_report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 print(f'[{name}] staged full retrain complete',flush=True)
