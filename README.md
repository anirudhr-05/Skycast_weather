# SkyCast Weather (By team Twin Titans)

A local weather dashboard written in Python, using only the standard library (no `pip install` needed). It shows live forecasts and air quality for any city, and includes an **Activity Window Finder** that suggests the best times in the next 48 hours for running, drying clothes, commuting on a two-wheeler, crop spraying and stargazing.


## Features

- **Current weather:** temperature, feels-like, humidity, wind, a short summary of the next 12 hours, and the best time to run
- **Hourly and 7-day forecast,** plus a 24-hour temperature chart
- **Air quality:** US AQI, PM2.5, PM10, ozone and NO₂
- **Weather alerts:** rain now or soon, heat, high UV, strong gusts, poor air quality, and big temperature drops
- **Activity Window Finder:** ranks the best time slots in the next 48 hours for 5 activities and shows the reasons (✓ good / ⚠ watch out)
- **City search:** add any city and switch between saved cities. Your list is saved in the browser
- **°C / °F toggle,** manual refresh, and auto-refresh every 5 minutes
- **Offline demo mode:** if there's no internet, the app uses built-in sample data and clearly labels it as demo data

## Requirements

- Python 3.8 or newer
- An internet connection for live data (the app still runs without one, using demo data)

No third-party packages are needed.

## How to run

```bash
python skycast_weather.py
```

Your browser opens `http://127.0.0.1:8000` automatically. If it doesn't, open that address yourself. Press `Ctrl+C` in the terminal to stop the server.

## How it works

```
Browser page  ──►  Python server (http.server)  ──►  Open-Meteo APIs
 (HTML/CSS/JS)        /api/skycast/...                forecast, air quality, geocoding
```

1. The Python server serves the dashboard page and a small JSON API.
2. For each city, it requests the forecast and air quality from Open-Meteo. Responses are cached for 2 minutes.
3. It turns the raw data into current conditions, alerts and activity windows, then sends the result to the page as JSON.
4. If the forecast request fails, it switches to demo data. If only the air-quality request fails, the page shows "AQI unavailable" instead of a made-up number.

### Activity Window Finder

Each activity is defined as data, not separate code:

- **Rules:** a list of weather factors with a weight and an "ideal range". For example, a run prefers 14–24 °C, low rain chance, low UV and clean air. Each hour gets a score from 0 to 100 for how close conditions are to ideal.
- **Vetoes:** hard limits that cap the score. For example, a rain chance above 60% caps a run at 35.
- **Time rules:** allowed hours (for example, crop spraying only 5–10 AM and 4–7 PM), and daytime-only or night-only activities.

The app slides a window over the next 48 hours, scores every possible slot, and shows the top 3 slots that don't overlap.

These thresholds are my own rule-of-thumb values for a demo project. They are not official meteorological or agricultural guidance.

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/skycast` | API info |
| `GET /api/skycast/weather?lat=13.08&lon=80.27&name=Chennai` | Weather, alerts and activity windows for a location |
| `GET /api/skycast/search?q=chennai` | City search (up to 5 results) |

An invalid `lat` or `lon` returns HTTP 400.

## Project structure

```
skycast_weather.py   # everything: server, API logic, activity scoring, and the dashboard page
README.md
```

## Limitations

- Runs locally only (`127.0.0.1`). It is not set up for public hosting.
- The dashboard HTML/CSS/JS is stored as one string inside the Python file.
- Activity scores come from simple fixed rules, not machine learning.
- There are no automated tests yet.

## Privacy

There are no accounts, tracking or API keys. The city coordinates you look up are sent to Open-Meteo to get the weather. Your saved cities stay in your own browser's local storage.

## Credits

Weather, air-quality and geocoding data by [Open-Meteo.com](https://open-meteo.com/).

