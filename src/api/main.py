from fastapi import FastAPI

app = FastAPI(title="Crop Recommendation Bot API")

@app.get("/")
async def root():
    return {"message": "Welcome to Crop Recommendation Bot API"}
