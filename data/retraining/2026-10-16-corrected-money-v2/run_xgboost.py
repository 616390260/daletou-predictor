"""Isolated native XGBoost audit; avoids the eager PyTorch model package import."""
import sys,types,json,time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path.cwd()))
package=types.ModuleType('backend.src.models');package.__path__=[str(Path.cwd()/'backend/src/models')]
sys.modules['backend.src.models']=package
from backend.src.models import xgboost_model as xm
import xgboost
root=Path(sys.argv[1]);source=json.loads((root/'input.json').read_text());history=pd.read_pickle(root/'history.pkl');train=history.iloc[:-60]
original_factory=xm.XGBoostModel._get_classifier_cls; fitted={'count':0}
def limited_factory(self):
 factory,backend=original_factory(self)
 assert backend=='xgboost','Native XGBoost is required, without fallback'
 def make():
  clf=factory().set_params(nthread=2,n_jobs=2)
  original_fit=clf.fit
  def fit(*args,**kwargs):
   result=original_fit(*args,**kwargs);fitted['count']+=1;return result
  clf.fit=fit
  return clf
 return make,backend
xm.XGBoostModel._get_classifier_cls=limited_factory
model=xm.XGBoostModel();start=time.time();preds=[];labels=[]
for is_front in [True,False]:
 X,y,_=xm._build_dataset(train,is_front)
 future_X=[];truth=[];key='front' if is_front else 'back';k=35 if is_front else 12
 for i in range(len(train),len(history)):
  _,_,last=xm._build_dataset(history.iloc[:i],is_front);future_X.append(last)
  row=np.zeros(k);row[np.array(history.iloc[i][key])-1]=1;truth.append(row)
 future_X=np.stack(future_X);p=np.zeros((60,k));factory,_=model._get_classifier_cls()
 for n in range(k):
  clf=factory();clf.fit(X,y[:,n].astype(int));p[:,n]=clf.predict_proba(future_X)[:,1]
 preds.append(p);labels.append(np.stack(truth))
 print(f'XGBoost validated {key}: {k} native classifiers',flush=True)
p=np.concatenate(preds,axis=1);y=np.concatenate(labels,axis=1)
assert fitted['count']==47 and np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
np.savez(root/'xgboost_validation.npz',issues=np.array(source['validation_issues']),probabilities=p,labels=y)
safe=np.clip(p,1e-7,1-1e-7)
validation=dict(log_loss=float(-(y*np.log(safe)+(1-y)*np.log1p(-safe)).mean()),brier=float(((p-y)**2).mean()),classifiers=47)
print('XGBoost validation',validation,flush=True)
xm.CACHE_PATH=root/'staged/xgboost_probs.npz'
front,back=model._cached_probs(history)
assert fitted['count']==94,'All 47 full-data classifiers must fit successfully'
assert front.shape==(35,) and back.shape==(12,) and np.isfinite(np.r_[front,back]).all()
result=dict(validation=validation,full_training=dict(last_trained_issue=source['last_issue'],training_rows=len(history),supervised_examples=len(history)-xm.WINDOW,backend='native_xgboost',library_version=xgboost.__version__,classifiers=47,max_depth=4,n_estimators=80,learning_rate=0.1,nthread=2,mode='full',training_data_sha256=source['data_sha256']),duration_seconds=round(time.time()-start,2))
(root/'xgboost_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('XGBoost staged full retrain complete',flush=True)
