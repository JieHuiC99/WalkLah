
# WalkLah

WalkLah is a pedestrian navigation and obstacle-reporting
prototype for Malaysian townships.

## Features

- Pedestrian-network route calculation
- Baseline and obstacle-aware route comparison
- Community obstacle reports
- Operator verification workflow
- Infrastructure insights dashboard

## Technology

Frontend: React, TypeScript, Vite, MapLibre
Backend: Python, FastAPI, NetworkX, OSMnx
Map data: OpenStreetMap

## Requirements

- Git
- Node.js and npm
- Python 3.11 or another version confirmed compatible
  with the selected OSMnx release
- A modern browser

## Setup

See the setup instructions in this README or the developer
build guide.

## Project structure

- frontend/: user interface
- backend/: API, pedestrian routing and report logic
- docs/: API contract, workflow and demo script

## Data and limitations

This prototype uses OpenStreetMap data for pedestrian routing.
Map completeness and pedestrian accessibility may vary.

Demo verification is not proof of physical inspection.
Real deployment requires report moderation, authentication,
appropriate privacy controls and field validation.

## Attribution

Display appropriate OpenStreetMap attribution on the map
and comply with the applicable data and tile-provider terms.