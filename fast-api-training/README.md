### Step 1: Install Required Packages

You will need to install the following packages for your FastAPI application:

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary
```

- `fastapi`: The web framework for building APIs.
- `uvicorn`: ASGI server for running FastAPI applications.
- `sqlalchemy`: ORM for database interactions.
- `psycopg2-binary`: PostgreSQL adapter for Python.

### Step 2: Create the FastAPI Application

Create a new file named `main.py` in your project directory. Below is a sample implementation of a FastAPI application that connects to a PostgreSQL database and implements user functionality similar to your existing Node.js application.

```python
# filepath: /Users/robifirmansyah/Documents/backend-magnasight-fastapi/main.py
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import bcrypt
import jwt
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://magna:M@gn@123@localhost:5432/support_ticket_db")

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# User model
class User(Base):
    __tablename__ = "users"
    
    id_user = Column(String, primary_key=True, index=True)
    full_name = Column(String)
    username = Column(String, unique=True)
    password = Column(String)
    company_id = Column(String)
    role = Column(String)
    email = Column(String)
    phone = Column(String)

# Pydantic models
class UserCreate(BaseModel):
    full_name: str
    username: str
    password: str
    company_id: str
    role: str = "Customer"
    email: str
    phone: str

class UserResponse(BaseModel):
    id_user: str
    full_name: str
    username: str
    role: str
    email: str
    phone: str

# FastAPI app
app = FastAPI()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create user
@app.post("/users/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    db_user = User(**user.dict(), password=hashed_password.decode('utf-8'))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# User login
@app.post("/users/login")
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = jwt.encode({"id_user": user.id_user, "role": user.role}, "A1b2C3d4E5f6G7h8I9J0kLmNoPqRsTuVwXyZ1234567890!@#$%^&*()", algorithm="HS256")
    return {"token": token, "user": user}

# Get all users
@app.get("/users/", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)  # Use a different port to avoid conflict
```

### Step 3: Run the FastAPI Application

You can run the FastAPI application using the following command:

```bash
uvicorn main:app --reload
```

This will start the FastAPI application on `http://127.0.0.1:8001`, allowing it to run alongside your existing Node.js application on `http://localhost:8000`.

### Summary

This FastAPI application includes user registration and login functionality, similar to your Node.js application. It connects to a PostgreSQL database and uses SQLAlchemy for ORM. Make sure to adjust the database connection string as needed and ensure that the database schema matches the expected structure.