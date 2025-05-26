from typing import Union
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import users, customers, tickets, groups, projects, services
from database import connect_to_db, close_db_connection

app = FastAPI(title="Magnasight API", version="0.2.0")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sight.arfarays.com", "https://sight.magnaglobal.id", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    app.state.db = await connect_to_db()

@app.on_event("shutdown")
async def shutdown():
    await close_db_connection(app.state.db)

app.include_router(customers.router, prefix="/api/customers", tags=["Customers"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(groups.router, prefix="/api/groups", tags=["Groups"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(services.router, prefix="/api/services", tags=["Services"])


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}