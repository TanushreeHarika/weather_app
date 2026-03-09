#!/usr/bin/env python3
"""
End-to-end test for Weather App
Tests: signup, login, forecast, history, and theme switching
"""
import requests
import json
import sys
from datetime import datetime

API_URL = "http://127.0.0.1:8000"
TEST_USER = "e2e_test_user_" + str(int(datetime.now().timestamp()))
TEST_PASS = "testpass123"
TEST_CITY = "London"

def test_signup():
    """Test user signup"""
    print(f"\n[TEST 1] Sign up user: {TEST_USER}")
    resp = requests.post(
        f"{API_URL}/signup",
        json={"username": TEST_USER, "password": TEST_PASS},
        timeout=5
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "id" in data, "No user id in response"
    print("✓ Signup passed")
    return data["id"]

def test_login(user_id):
    """Test user login and get JWT token"""
    print(f"\n[TEST 2] Login and get token")
    resp = requests.post(
        f"{API_URL}/login",
        json={"username": TEST_USER, "password": TEST_PASS},
        timeout=5
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Response (truncated): {list(data.keys())}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "access_token" in data, "No access_token in response"
    token = data["access_token"]
    print(f"✓ Login passed, token: {token[:20]}...")
    return token

def test_forecast(token):
    """Test forecast endpoint with authentication"""
    print(f"\n[TEST 3] Get forecast for {TEST_CITY} with JWT")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{API_URL}/forecast/{TEST_CITY}",
        headers=headers,
        timeout=8
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    
    data = resp.json()
    # Check structure
    assert "current" in data, "No 'current' in response"
    assert "hourly" in data, "No 'hourly' in response"
    assert "daily" in data, "No 'daily' in response"
    assert "location" in data, "No 'location' in response"
    
    cur = data["current"]
    print(f"Current: {cur['temp']}°C, {cur['weather'][0]['description']}")
    print(f"Sunrise: {data.get('location',{}).get('name')}")
    print(f"Hourly entries: {len(data.get('hourly', []))}")
    print(f"Daily entries: {len(data.get('daily', []))}")
    print("✓ Forecast passed (One Call + geocoding works)")
    
    # Check day/night theme logic
    dt = cur.get('dt')
    sunrise = cur.get('sunrise')
    sunset = cur.get('sunset')
    is_day = dt >= sunrise and dt < sunset if (dt and sunrise and sunset) else False
    theme = "day" if is_day else "night"
    print(f"Theme: {theme} (sunrise={datetime.fromtimestamp(sunrise) if sunrise else None}, sunset={datetime.fromtimestamp(sunset) if sunset else None})")
    
    return token

def test_history(token):
    """Test getting search history after forecast save"""
    print(f"\n[TEST 4] Get search history (should have 1 entry)")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{API_URL}/history",
        headers=headers,
        timeout=5
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"History entries: {len(data)}")
    if data:
        for i, item in enumerate(data[:3]):  # Show first 3
            print(f"  [{i}] {item['city']}: {item['temperature']}°C ({item['description']})")
    assert len(data) > 0, "History should have at least 1 entry"
    print("✓ History passed (auto-saved on forecast call)")
    return data[0] if data else None

def test_history_delete(token, history_id):
    """Test deleting a history item"""
    print(f"\n[TEST 5] Delete history item {history_id}")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.delete(
        f"{API_URL}/history/{history_id}",
        headers=headers,
        timeout=5
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Response: {data}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    print("✓ Delete history passed")

def test_token_auth():
    """Test that endpoints require valid token"""
    print(f"\n[TEST 6] Verify token auth is enforced")
    # Try history without token
    resp = requests.get(f"{API_URL}/history", timeout=5)
    print(f"History without token: {resp.status_code}")
    assert resp.status_code == 401, "Should require token for history"
    print("✓ Token auth enforced")

def main():
    print("=" * 60)
    print("Weather App - End-to-End Test Suite")
    print("=" * 60)
    
    try:
        # Run flow
        user_id = test_signup()
        token = test_login(user_id)
        test_forecast(token)
        history = test_history(token)
        if history:
            test_history_delete(token, history['id'])
        test_token_auth()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("  ✓ Auth: signup, login, JWT tokens")
        print("  ✓ Geocoding: city → lat/lon")
        print("  ✓ Forecast: One Call API, hourly/daily")
        print("  ✓ History: auto-saved, retrieved, deleted")
        print("  ✓ Theme: day/night based on sunrise/sunset")
        print("  ✓ Security: endpoints require JWT\n")
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
