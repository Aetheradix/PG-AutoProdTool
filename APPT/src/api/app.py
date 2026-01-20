from fastapi import FastAPI

app = FastAPI(title="Auto Production Planning API")


@app.get("/")
def root():
    return {"message":"Auto Production Planning API"}
