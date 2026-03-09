
import os
import requests
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from passlib.context import CryptContext
from dotenv import load_dotenv
from datetime import datetime
import jwt
from datetime import timedelta
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Load environment variables
load_dotenv()

# Use SQLite for local development (no MySQL required)
DB_URL = "sqlite:///./weather_app.db"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True)
    password = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    search_history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")

class SearchHistory(Base):
    __tablename__ = "search_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    city = Column(String(100))
    temperature = Column(Float)
    description = Column(String(255))
    searched_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="search_history")

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

security = HTTPBearer(auto_error=False)


# *** THIS FUNCTION WAS MOVED TO THE TOP - THIS FIXES THE ERROR ***
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user_from_token_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            return None
    except jwt.PyJWTError:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user


def get_current_user_from_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


class AuthRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str


class HistoryItem(BaseModel):
    id: int
    city: str
    temperature: float
    description: str
    searched_at: str

@app.get("/")
def read_root():
    return {"message": "Weather API with MySQL is running!"}


@app.post("/signup", response_model=UserResponse)
def signup(payload: AuthRequest, db: Session = Depends(get_db)):
    u = payload.username
    p = payload.password
    existing_user = db.query(User).filter(User.username == u).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_password = pwd_context.hash(p)
    new_user = User(username=u, password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username}

@app.post("/login")
def login(payload: AuthRequest, db: Session = Depends(get_db)):
    u = payload.username
    p = payload.password
    user = db.query(User).filter(User.username == u).first()
    if not user or not pwd_context.verify(p, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token({"user_id": user.id, "username": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "username": user.username}

@app.get("/weather/{city}")
def get_weather(city: str, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_from_token_optional)):
    if not WEATHER_API_KEY:
        raise HTTPException(status_code=500, detail="WEATHER_API_KEY not configured")
    params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}
    try:
        response = requests.get(WEATHER_BASE_URL, params=params, timeout=8)
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Failed to fetch weather data")
    if response.status_code != 200:
        try:
            err = response.json()
            detail = err.get('message', 'Weather data error')
        except Exception:
            detail = 'Weather data error'
        raise HTTPException(status_code=response.status_code, detail=detail)
    data = response.json()
    if current_user:
        try:
            temperature = data["main"]["temp"]
            description = data["weather"][0]["description"]
            search_record = SearchHistory(user_id=current_user.id, city=city, temperature=temperature, description=description)
            db.add(search_record)
            db.commit()
        except Exception:
            db.rollback()
    return data

@app.get("/forecast/{city}")
def get_forecast(city: str, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_from_token_optional)):
    # Demo mode: return sample data if no API key is configured
    if not WEATHER_API_KEY or WEATHER_API_KEY == "your_openweathermap_api_key":
        # Return demo data with different times based on city name hash
        import hashlib
        
        # Generate a consistent offset based on city name
        city_hash = int(hashlib.md5(city.encode()).hexdigest(), 16) % 24
        timezone_offset = (city_hash - 12) * 3600  # -12 to +12 hours offset
        
        current_time = int(datetime.now().timestamp())
        local_time = current_time + timezone_offset
        
        # Calculate sunrise/sunset based on a typical 6am-6pm day
        sunrise_local = 6 * 3600  # 6 AM local
        sunset_local = 18 * 3600  # 6 PM local
        
        # Convert to Unix timestamps
        day_start = (local_time // 86400) * 86400
        sunrise_today = day_start + sunrise_local - timezone_offset
        sunset_today = day_start + sunset_local - timezone_offset
        
        # Determine if it's day or night in the city's local time
        local_hour = (local_time % 86400) // 3600
        is_day = 6 <= local_hour < 18
        weather_icon = "01d" if is_day else "01n"
        weather_id = 800 if is_day else 800
        
        demo_data = {
            "current": {
                "dt": current_time,
                "temp": 22 + (city_hash % 10),
                "feels_like": 21 + (city_hash % 10),
                "humidity": 60 + (city_hash % 20),
                "pressure": 1010 + (city_hash % 10),
                "wind_speed": 2 + (city_hash % 5),
                "wind_deg": (city_hash * 10) % 360,
                "weather": [{"id": weather_id, "main": "Clear", "description": "clear sky", "icon": weather_icon}],
                "clouds": (city_hash % 30),
                "visibility": 10000,
                "uvi": 5 if is_day else 0,
                "sunrise": sunrise_today,
                "sunset": sunset_today,
                "timezone": timezone_offset
            },
            "hourly": [
                {"dt": current_time + i*3600, "temp": 20 + (city_hash % 10) + i%5, "feels_like": 19 + (city_hash % 10) + i%5, 
                 "humidity": 55 + (city_hash % 20) + i%5, 
                 "pressure": 1010 + (city_hash % 10), 
                 "wind_speed": 2 + (city_hash % 5), 
                 "wind_deg": (city_hash * 10) % 360, 
                 "weather": [{"id": weather_id, "main": "Clear", "description": "clear sky", "icon": weather_icon}],
                 "clouds": (city_hash % 30), "visibility": 10000, "pop": 0}
                for i in range(24)
            ],
            "daily": [
                {"dt": current_time + i*86400, 
                 "temp": {"min": 16 + i + (city_hash % 5), "max": 24 + i + (city_hash % 5)}, 
                 "weather": [{"id": weather_id, "main": "Clear", "description": "clear sky", "icon": weather_icon}], 
                 "pop": 0.1}
                for i in range(8)
            ],
            "location": {
                "name": city.title(),
                "country": "Demo",
                "lat": 28.6139 + (city_hash % 50) / 10,
                "lon": 77.2090 + (city_hash % 50) / 10
            }
        }
        return demo_data
    
    # Get current weather
    params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}
    try:
        response = requests.get(WEATHER_BASE_URL, params=params, timeout=8)
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Failed to fetch weather data")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json().get('message', 'Weather data error'))
    
    current_data = response.json()
    
    # Get 5-day forecast
    try:
        forecast_resp = requests.get(FORECAST_URL, params=params, timeout=8)
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Failed to fetch forecast data")
    if forecast_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Forecast error")
    
    forecast_data = forecast_resp.json()
    
    # Transform to One Call API format for frontend compatibility
    hourly = []
    for item in forecast_data.get('list', [])[:24]:
        hourly.append({
            "dt": item['dt'],
            "temp": item['main']['temp'],
            "feels_like": item['main']['feels_like'],
            "humidity": item['main']['humidity'],
            "pressure": item['main']['pressure'],
            "wind_speed": item['wind'].get('speed', 0),
            "wind_deg": item['wind'].get('deg', 0),
            "weather": item['weather'],
            "clouds": item['clouds'].get('all', 0),
            "visibility": item.get('visibility', 10000),
            "pop": item.get('pop', 0)
        })
    
    # Group by day for daily forecast
    daily_list = {}
    for item in forecast_data.get('list', []):
        day = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
        if day not in daily_list:
            daily_list[day] = []
        daily_list[day].append(item)
    
    daily = []
    for day, items in list(daily_list.items())[:8]:
        temps = [item['main']['temp'] for item in items]
        weather = items[len(items)//2]['weather']
        daily.append({
            "dt": items[0]['dt'],
            "temp": {"min": min(temps), "max": max(temps)},
            "weather": weather,
            "pop": max([item.get('pop', 0) for item in items])
        })
    
    # Get sunrise/sunset from current weather
    sunrise = current_data.get('sys', {}).get('sunrise', 0)
    sunset = current_data.get('sys', {}).get('sunset', 0)
    
    result = {
        "current": {
            "dt": current_data.get('dt', 0),
            "temp": current_data['main']['temp'],
            "feels_like": current_data['main']['feels_like'],
            "humidity": current_data['main']['humidity'],
            "pressure": current_data['main']['pressure'],
            "wind_speed": current_data['wind'].get('speed', 0),
            "wind_deg": current_data['wind'].get('deg', 0),
            "weather": current_data['weather'],
            "clouds": current_data.get('clouds', {}).get('all', 0),
            "visibility": current_data.get('visibility', 10000),
            "uvi": 0,
            "sunrise": sunrise,
            "sunset": sunset
        },
        "hourly": hourly,
        "daily": daily,
        "location": {
            "name": current_data.get('name', city),
            "country": current_data.get('sys', {}).get('country', ''),
            "lat": current_data.get('coord', {}).get('lat', 0),
            "lon": current_data.get('coord', {}).get('lon', 0)
        }
    }
    
    if current_user:
        try:
            temperature = current_data["main"]["temp"]
            description = current_data["weather"][0]["description"]
            search_record = SearchHistory(user_id=current_user.id, city=city, temperature=temperature, description=description)
            db.add(search_record)
            db.commit()
        except Exception:
            db.rollback()
    
    return result

@app.get("/history", response_model=List[HistoryItem])
def get_search_history(current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    history = db.query(SearchHistory).filter(SearchHistory.user_id == current_user.id).order_by(SearchHistory.searched_at.desc()).all()
    return [{"id": item.id, "city": item.city, "temperature": item.temperature, "description": item.description, "searched_at": item.searched_at.strftime("%Y-%m-%d %H:%M:%S")} for item in history]

@app.delete("/history/{history_id}")
def delete_history_item(history_id: int, current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    item = db.query(SearchHistory).filter(SearchHistory.id == history_id, SearchHistory.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    db.delete(item)
    db.commit()
    return {"message": "History item deleted"}
