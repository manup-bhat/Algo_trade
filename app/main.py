from fastapi import FastAPI
import threading

from app.kite_ws import start_kite
from app.store import signals

app = FastAPI()

@app.on_event("startup")
def startup():
    threading.Thread(target=start_kite).start()

@app.get("/")
def home():
    return {"msg": "Scanner running"}

@app.get("/signals")
def get_signals():
    return signals[-20:]