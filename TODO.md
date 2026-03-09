# Weather App - Project Plan

## ✅ COMPLETED
- [x] Backend: SQLite integration with SQLAlchemy
- [x] Backend: User authentication (signup/login with bcrypt password hashing)
- [x] Backend: Search history model and endpoints
- [x] Frontend: Search history UI display
- [x] Frontend: Click on history to re-search city
- [x] Frontend: Delete history items
- [x] Created requirements.txt
- [x] Fixed bcrypt compatibility issue (bcrypt==4.0.1)
- [x] Day/night background transitions based on city timezone

## 📋 Environment Variables (.env)
```
MYSQL_PASSWORD=root123
WEATHER_API_KEY=your_openweathermap_api_key
JWT_SECRET=dev-secret-change-this
```

## 🗄️ Database
- **SQLite** (file-based, no setup required)
- Database file: `weather_app.db`

## 🚀 To Run the App
1. Install dependencies: `pip install -r requirements.txt`
2. Start backend: `cd back_end && uvicorn main:app --host 127.0.0.1 --port 8000`
3. Open frontend: `front_end/index.html` in browser

## ⚠️ Note
- You need to add your OpenWeatherMap API key to the `.env` file for weather data to work
- Get free API key at: https://openweathermap.org/api

## 🔄 Making Changes & Pushing
1. Make changes in local folder
2. Stage: `git add .`
3. Commit: `git commit -m "Your message"`
4. Push: `git push`

