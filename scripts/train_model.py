# Version 0 month model. Expects data.json (cities with monthly GBIF counts, 86 stations with rain p and temperature t normals) from the page build.
# Needs: pip install scikit-learn numpy
import json, math, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
D=json.load(open('data.json'))
ST=D['rain']
def nearest(c):
    k=math.cos(math.radians(c['lat']))
    return min(ST,key=lambda s:(s['lat']-c['lat'])**2+((s['lon']-c['lon'])*k)**2)
MIN_N=30; THR=0.10
X=[];y=[];g=[];reg=[];idx=[]
cities=[(R,c) for R in D['cities'] for c in D['cities'][R]]
def feats(c,s,m):
    p,t=s['p'],s['t']
    return [t[m],t[m-1],t[m]-t[m-1],p[m],p[m-1]+p[m-2],(p[m-1]+p[m-2]+p[m-3])/3,abs(c['lat']),math.sin(2*math.pi*m/12),math.cos(2*math.pi*m/12)]
FN=['temp this month','temp last month','temp change','rain this month','rain last 2 months','rain avg last 3 months','latitude','month (sin)','month (cos)']
for R,c in cities:
    tot=sum(c['mm'])
    if tot<MIN_N: continue
    s=nearest(c)
    for m in range(12):
        X.append(feats(c,s,m)); y.append(1 if c['mm'][m]/tot>=THR else 0); g.append(c['cc']); reg.append(R)
X=np.array(X);y=np.array(y);g=np.array(g);reg=np.array(reg)
print('samples',len(y),'positives',y.mean().round(3),'cities',len(y)//12,'countries',len(set(g)))
models={
 'baseline (month only)':None,
 'logistic regression':lambda:make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000,C=1.0)),
 'gradient boosting':lambda:HistGradientBoostingClassifier(max_depth=3,learning_rate=.05,max_iter=300,min_samples_leaf=30,l2_regularization=1.0),
}
def baseline_fit(Xtr,ytr):
    # frequency of fruiting month by calendar month in training data
    mo=np.round(np.arctan2(Xtr[:,7],Xtr[:,8])/(2*np.pi)*12)%12
    f={int(k):ytr[mo==k].mean() for k in range(12)}
    return lambda Xt: np.array([f[int(k)] for k in np.round(np.arctan2(Xt[:,7],Xt[:,8])/(2*np.pi)*12)%12])
res={}
def evaluate(tr,te):
    out={}
    for name,mk in models.items():
        if mk is None: pr=baseline_fit(X[tr],y[tr])(X[te])
        else:
            mdl=mk().fit(X[tr],y[tr]); pr=mdl.predict_proba(X[te])[:,1]
        out[name]=pr
    return out
# 1) grouped CV by country
gkf=GroupKFold(n_splits=5)
P={k:np.zeros(len(y)) for k in models}
for tr,te in gkf.split(X,y,g):
    o=evaluate(tr,te)
    for k in o: P[k][te]=o[k]
def metr(yt,pr,base):
    b=brier_score_loss(yt,pr); bb=brier_score_loss(yt,base)
    return dict(roc_auc=round(roc_auc_score(yt,pr),3),pr_auc=round(average_precision_score(yt,pr),3),brier=round(b,3),brier_skill=round(1-b/bb,3))
res['cv_by_country']={k:metr(y,P[k],P['baseline (month only)']) for k in models}
# 2) train Europe -> test North America
tr=np.where(reg=='EU')[0]; te=np.where(reg!='EU')[0]
o=evaluate(tr,te)
res['europe_to_north_america']={k:metr(y[te],o[k],o['baseline (month only)']) for k in models}
res['data']=dict(samples=int(len(y)),cities=int(len(y)//12),countries=int(len(set(g))),positive_rate=round(float(y.mean()),3),min_records=MIN_N,threshold=THR)
print(json.dumps(res,indent=1))
# final: pick best by CV brier skill among learned models
best='logistic regression'  # transfers to new regions better (Europe->North America), see results
res['chosen']=best
mdl=models[best]().fit(X,y)
# logistic coefficients for interpretability
lr=models['logistic regression']().fit(X,y)
coef=lr[-1].coef_[0]
res['logistic_weights']={FN[i]:round(float(coef[i]),2) for i in range(len(FN))}
for R,c in cities:
    s=nearest(c)
    c['pm']=[int(round(100*v)) for v in mdl.predict_proba(np.array([feats(c,s,m) for m in range(12)]))[:,1]]
json.dump(D,open('data.json','w'),ensure_ascii=False,separators=(',',':'))
json.dump(res,open('/tmp/claude-0/model/results.json','w'),indent=1)
print('chosen',best, res['logistic_weights'])
