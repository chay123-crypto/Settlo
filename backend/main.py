from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import agent as agent_module
from . import razorpay_client
from .pipeline import run_batch

app = FastAPI(title="Settlo API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/razorpay/status")
def razorpay_status():
    """Shows whether the app is in mock mode or hitting live Razorpay Test Mode."""
    return razorpay_client.connectivity_check()


@app.post("/batches/run")
def run(batch_id: str = None):
    try:
        return run_batch(batch_id=batch_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


class AgentQuery(BaseModel):
    question: str
    batch_id: str


@app.post("/agent/query")
def agent_query(payload: AgentQuery):
    try:
        return agent_module.ask(payload.question, payload.batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
