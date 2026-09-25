from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .jobs import JobManager
from .models import CheckRequest,JobCreated,JobStatus,CardResultOut,ListingOut
BASE=Path(__file__).resolve().parent.parent
app=FastAPI(title='Hareruya Spyglass',version='1.0.0'); manager=JobManager()
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
@app.get('/',include_in_schema=False)
def index(): return FileResponse(BASE/'static'/'index.html')
@app.get('/api/health')
def health(): return {'status':'ok'}
@app.post('/api/jobs',response_model=JobCreated)
def create(req:CheckRequest):
    cards=[]; seen=set()
    for x in req.cards:
        x=' '.join(x.split()).strip()
        if x and x.casefold() not in seen: cards.append(x); seen.add(x.casefold())
    if not cards: raise HTTPException(400,'No card names were supplied.')
    return JobCreated(job_id=manager.create(cards,req.finish,req.output).job_id)
@app.get('/api/jobs/{jid}',response_model=JobStatus)
def get(jid):
    j=manager.get(jid)
    if not j: raise HTTPException(404,'Job not found.')
    results=[CardResultOut(card_name=r.card_name,error=r.error,rows=[ListingOut(price=x.price,language=x.language,expansion=x.expansion,foil=x.foil,title=x.title,stock=x.stock,url=x.url,image_url=x.image_url) for x in r.rows]) for r in j.results]
    return JobStatus(job_id=j.job_id,status=j.status,completed=j.completed,total=len(j.cards),results=results,error=j.error,output=j.output)
