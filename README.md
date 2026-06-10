# ChoreTracker Pro 🌟

ChoreTracker Pro is a premium, containerized daily chore management web application designed for families. It provides a visual, interactive interface for kids to check off their daily chores by uploading photo proof, while giving parents full visibility of their children's progress via an interactive monthly progress calendar.

## 🚀 Key Features

* **Three Role Levels**:
  * **System Admin**: Manage parent accounts.
  * **Parents**: Register children, create/assign chores, and track completion status on a calendar.
  * **Children**: View daily chore assignments and upload verification photos.
* **Security & Reset Flows**: 
  * Bootstrapped default admin credentials.
  * Secure password hashing with `bcrypt`.
  * Temporary password generation for new users, forcing password reset on first login.
* **Strict Date Boundaries**: Kids can only complete chores for today or past dates; future chores are locked down.
* **Interactive Progress Calendar**: Displays completion status matrix dots for each child (emerald green for completed, red for incomplete).
* **Glassmorphism Dark UI**: A visually stunning dashboard built with modern Outfit typography, neon accents, floating glow states, and smooth CSS animations.

---

## 🛠️ Tech Stack

* **Backend**: Python 3.11, Flask
* **Database**: MongoDB 6.0
* **Frontend**: Vanilla HTML5, Vanilla CSS3 (Glassmorphic dark design), Vanilla JS (Single Page Application architecture)
* **Containerization**: Docker & Docker Compose

---

## 📂 Project Directory Structure

```
chore-tracking/
├── Dockerfile               # Container build configuration for Flask app
├── docker-compose.yml       # Service orchestration (web and mongo containers)
├── requirements.txt         # Python dependencies
├── app.py                   # Main Flask application and REST API routes
├── templates/
│   └── index.html           # Main Single Page App HTML template
├── static/
│   ├── css/
│   │   └── styles.css       # Core stylesheet (glassmorphic dark design)
│   ├── js/
│   │   └── app.js           # Client-side router, calendar rendering, and form APIs
│   └── uploads/             # Mounted directory for child verification images
└── tests/
    ├── dummy.png            # Asset for test uploads
    └── test_api.py          # API integration tests suite
```

---

## ⚙️ Quick Start

### 1. Prerequisites
Ensure you have [Docker](https://www.docker.com/) and Docker Compose installed.

### 2. Build and Start Services
Run the following command in the project root to build the container images and launch the services:
```bash
docker-compose up --build
```
This starts:
* **db**: MongoDB container listening on port `27017` with persistent data volume `mongo-data`.
* **web**: Flask Python container listening on port `5000` with persistent upload volume `chore-uploads`.

Once started, access the application in your browser at:
👉 **[http://localhost:5000](http://localhost:5000)**

### 3. Stop Services
To stop and remove containers and networks, run:
```bash
docker-compose down
```

### 4. Local Development Mode (Outside Docker Container)
For rapid code editing, debugging, or frontend hot reloading, you can run the Flask server locally on your host machine while keeping the MongoDB database in a Docker container:

1. **Boot Local Server**:
   Execute the automated developer script in the root directory:
   ```bash
   ./run_dev.sh
   ```
   This script will verify Docker is active, start and check the health of the MongoDB Docker container, map the DB port `27017` to localhost, automatically bootstrap/activate the Python virtual environment, install requirements.txt dependencies, and launch the Flask development server (defaulting to port `5000`, or automatically falling back to `5001` if port `5000` is already occupied).

2. **Access local server**:
   Navigate to the URL printed by the script: **[http://localhost:5000](http://localhost:5000)** (or **[http://localhost:5001](http://localhost:5001)**).

3. **Stop database**:
   To stop the background MongoDB database container and clean up its resources, run:
   ```bash
   docker-compose down
   ```

---

## 🔑 Login Workflows & Initial Setup

### Step 1: Admin Configuration
1. Log in with the default admin account:
   * **Username**: `admin`
   * **Password**: `admin`
2. You will be prompted to change your password immediately.
3. Once changed, you can register parent accounts (e.g. `parent_john`). When created, a temporary password will be generated. Copy this password.

### Step 2: Parent Setup
1. Log out of the admin panel.
2. Log in with the parent's username and temporary password.
3. Change the password.
4. Navigate to **Kids Manager** tab and register a child (e.g. `kid_sammy`). Copy their temporary password.
5. Navigate to **Chore Manager** tab, click **Add Chore**, enter title, description, and assign it to the child.

### Step 3: Kid Work
1. Log in with the child's username and temporary password.
2. Change the password.
3. On the dashboard, view assigned chores. Click **Mark Complete** on a chore card.
4. Upload a photo showing proof and submit. The chore will show a glowing green completed status.

---

## 🧪 Running the Test Suite

We include a comprehensive unit and integration test suite in `tests/test_api.py`. The suite tests backend authentications, roles, temporary password changes, parent/child user creation, chore operations, and date logic.

To run tests inside the container environment:
```bash
# Copy tests folder inside running container
docker cp tests chore_tracker_web:/app/tests

# Run test suite
docker exec -t chore_tracker_web python -m unittest tests/test_api.py
```
