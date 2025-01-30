# Rainfall Sensor Dashboard

[![Netlify Status](https://api.netlify.com/api/v1/badges/9e42b6a5-747c-4678-ac37-4dc28622cd2a/deploy-status)](https://app.netlify.com/sites/rainfallmonitoring/deploys)

This is a simple web application that displays rainfall data in real-time using Flask for the backend and React for the frontend.

## Backend

The backend is built using Flask and serves real-time rainfall data using Flask-SocketIO.

### Requirements

- Flask
- Flask-SocketIO
- eventlet
- Flask-CORS

### Setup

1. Navigate to the `rainfall-sensor-dashboard` directory:

    ```bash
    cd rainfall-sensor-dashboard
    ```

2. Create a virtual environment:

    ```bash
    python3 -m venv venv
    ```

3. Activate the virtual environment:

    ```bash
    source venv/bin/activate  # On Unix or MacOS
    venv\Scripts\activate     # On Windows
    ```

4. Install the dependencies:

    ```bash
    pip install -r requirements.txt
    ```

5. Run the Flask application:

    ```bash
    python app.py
    ```

## Frontend

The frontend is built using React and displays the rainfall data in real-time.

### Setup

1. Navigate to the `rainfall-sensor-dashboard` directory:

    ```bash
    cd rainfall-sensor-dashboard
    ```

2. Install the necessary dependencies:

    ```bash
    npm install
    ```

3. Create a `.env` file in the root of your project and add the backend URL:

    ```plaintext
    REACT_APP_BACKEND_URL=http://localhost:5000
    ```

4. Start the React development server:

    ```bash
    npm start
    ```

You should now have the React application running and connected to the Flask backend, displaying real-time rainfall data.

## Deployment

### Netlify Deployment

1. Create a `netlify.toml` file in the root of your project with the following content:

    ```toml
    [build]
      publish = "build"
      command = "npm run build"

    [[redirects]]
      from = "/api/*"
      to = "http://localhost:5000/:splat"
      status = 200
      force = true

    [[headers]]
      for = "/*"
      [headers.values]
        Access-Control-Allow-Origin = "*"
        Access-Control-Allow-Methods = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        Access-Control-Allow-Headers = "Content-Type, Authorization"
    ```

2. Deploy your site on Netlify.

### Status Badge

To track the status of your latest production deploy, the following badge has been added to your README:

[![Netlify Status](https://api.netlify.com/api/v1/badges/9e42b6a5-747c-4678-ac37-4dc28622cd2a/deploy-status)](https://app.netlify.com/sites/rainfallmonitoring/deploys)

---

By following these steps, you will have a fully functional Rainfall Sensor Dashboard with real-time data display and deployed status tracking.
