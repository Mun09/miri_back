from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio
from miri import run_analysis  # Import your core logic

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:3000",  # Next.js frontend
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A simple request model
class IdeaRequest(BaseModel):
    idea: str

@app.get("/")
async def read_root():
    return {"message": "MIRI Backend API is running."}

@app.post("/analyze")
async def analyze_idea(request: IdeaRequest):
    """
    Analyzes the business idea using the miri pipeline.
    """
    print(f"📥 Received Analysis Request: {request.idea[:50]}...")
    try:
        # Run the async analysis function from miri.py
        result = await run_analysis(request.idea)
        return result
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
