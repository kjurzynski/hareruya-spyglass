import threading, uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from .hareruya import CardResult, run_cards
@dataclass
class Job:
    job_id:str; cards:list[str]; finish:str; output:str; status:str='queued'; completed:int=0
    results:list[CardResult]=field(default_factory=list); error:str|None=None
class JobManager:
    def __init__(self,max_jobs=2): self.jobs={}; self.lock=threading.Lock(); self.pool=ThreadPoolExecutor(max_workers=max_jobs)
    def create(self,cards,finish,output):
        j=Job(str(uuid.uuid4()),cards,finish,output)
        with self.lock:self.jobs[j.job_id]=j
        self.pool.submit(self._run,j.job_id); return j
    def _run(self,jid):
        with self.lock:self.jobs[jid].status='running'
        def progress(c,_):
            with self.lock:self.jobs[jid].completed=c
        try:
            results=run_cards(self.jobs[jid].cards,self.jobs[jid].finish,progress)
            with self.lock:
                j=self.jobs[jid]; j.results=results; j.completed=len(j.cards); j.status='complete'
        except Exception as e:
            with self.lock:j=self.jobs[jid]; j.status='error'; j.error=str(e)
    def get(self,jid):
        with self.lock:
            j=self.jobs.get(jid)
            if not j:return None
            return Job(j.job_id,list(j.cards),j.finish,j.output,j.status,j.completed,list(j.results),j.error)
