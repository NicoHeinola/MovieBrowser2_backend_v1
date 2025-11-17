import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from middleware.query_parser import QueryParserMiddleware
from routers import shows, settings, auth, user_show_statuses, websites, user_watch_seasons
import uvicorn

load_dotenv(override=False)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

app = FastAPI()

# Query Parser Middleware - Add this before CORS to parse query params early
app.add_middleware(QueryParserMiddleware)

# CORS Middleware Configuration
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(shows.router, prefix="/shows")
app.include_router(settings.router, prefix="/settings")
app.include_router(auth.router, prefix="/auth")
app.include_router(websites.router, prefix="/websites")
app.include_router(user_watch_seasons.router, prefix="/user-watch-seasons")
app.include_router(user_show_statuses.router, prefix="/user-show-statuses")


@app.get("/")
def read_root():
    return {"message": "Welcome to MovieBrowser Backend"}


if __name__ == "__main__":
    is_dev_environment = ENVIRONMENT == "development"

    should_reload: bool = is_dev_environment
    uvicorn_app = "main:app" if is_dev_environment else app

    uvicorn.run(uvicorn_app, host="0.0.0.0", port=8077, reload=should_reload)
