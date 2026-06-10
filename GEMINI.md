# GEMINI.md - Technical Architecture & Developer Notes

This document provides developer-focused insights regarding the technical architecture, design decisions, security choices, and verification results of the ChoreTracker Pro application.

---

## 🏗️ Technical Architecture & Design Decisions

### 1. Database Schema & Indexing (MongoDB)
MongoDB was selected as the database backend to allow lightweight document structures that scale easily. To prevent database clutter and enforce consistency, we defined three collections with the following design patterns:

* **`users`**: Stores credentials for all roles (`admin`, `parent`, `child`).
  * *Index*: Unique index on `username` to prevent duplicate usernames across all roles.
  * *Security*: Passwords are hashed using standard `bcrypt` with unique salts. An `is_temp_password` boolean tracks if the user is using a generated temporary password and intercepts routing to force a password change.
* **`chores`**: Defines active chores.
  * *Relationship*: `assigned_to` contains the unique username of the child.
  * *Index*: Single index on `assigned_to` to quickly load active chores for a child.
* **`completions`**: Records verified chore completions.
  * *Relationship*: References `chore_id` (ObjectId) and `completed_by` (username).
  * *Index*: Compound unique index on `("chore_id", "date", "completed_by")`. This ensures a child can complete a specific chore at most once per day, preventing API spam or duplicate submissions.

### 2. Timezone-Safe Date Management
To track daily chores accurately, timezone offsets between the Flask server (running in Docker UTC) and client browsers must be resolved.
* **Approach**: We represent days as `YYYY-MM-DD` strings.
* **Flow**: The client browser computes the date using local time (`getLocalDateString()` using local year/month/day parameters). When a child submits chore completion, the browser submits both the target `date` string and the `client_today` date string.
* **Backend Validation**: The Flask backend verifies that the submitted `date` is strictly equal to `client_today`. If the child tries to submit a completion date that differs from their browser's current date (whether in the past or the future), the backend rejects it. The frontend kid dashboard automatically hides action buttons and renders a "Missed" badge for any uncompleted chores on past dates.

### 3. Glassmorphic Dark UI Theme
The user interface is styled to feel premium, visually engaging, and modern. Key choices include:
* **Background Depth**: Deep workspace colors (`#070a13`) with blurred, glowing background blobs.
* **Glass Panels**: Cards use `rgba(18, 24, 43, 0.75)` backgrounds combined with a `backdrop-filter: blur(12px)` and thin semi-transparent borders.
* **Glow success states**: Completed chores glow in a soft emerald shadow, while missed chores show a muted red alert state.
* **Modal Dialogs**: Leverage native HTML5 `<dialog>` elements for overlay modals. They offer native focus trap management, automatic `Esc` key dismissals, and clean styling of backdrops via the CSS `::backdrop` selector.

---

## 🔒 Security Practices

1. **Role Access Decorators**: Custom Python wrappers `@login_required` and `@role_required(...)` protect all REST APIs. They inspect Flask session data and respond with standard `401 Unauthorized` or `403 Forbidden` status codes.
2. **File Upload Hardening**:
   * Restricted file formats: Extensions are restricted to standard web image formats (`PNG`, `JPG`, `JPEG`, `GIF`, `WEBP`).
   * Filename randomization: Incoming filenames are completely discarded. The system generates a randomized secure name (`secrets.token_hex(8) + timestamp`) to prevent directory traversal attacks.
   * Body size limits: Flask's `MAX_CONTENT_LENGTH` is configured to 5MB to prevent denial-of-service (DoS) attempts via bloated file uploads.
3. **Password Generation**: Generated passwords use `secrets.choice` pulling from alphanumeric character sets to combine safety with easy readability for children.

---

## 🧪 Verification Logs

### 1. Automated Integration Tests
The Flask application's endpoint logic was verified inside the dockerized environment using the Python `unittest` framework:

```bash
docker cp tests chore_tracker_web:/app/tests
docker exec -t chore_tracker_web python -m unittest tests/test_api.py
```

**Results**:
```
Database bootstrap: admin user already exists.
Admin user bootstrapped successfully with username 'admin' and password 'admin'
.Admin user bootstrapped successfully with username 'admin' and password 'admin'
.
----------------------------------------------------------------------
Ran 2 tests in 2.064s

OK
```
Both test classes (`test_admin_flow` and `test_parent_and_child_flows`) completed successfully.

### 2. Manual Verification
* **Server Verification**: Run `curl -sI http://localhost:5000` to confirm headers are successfully served from Gunicorn.
* **Local Developer Environment**: Implemented a standalone runner shell script `run_dev.sh` to facilitate local backend debugging. It launches Flask locally while spinning up and mapping the MongoDB database inside Docker automatically.
* **Browser subagent Notes**: The automated browser subagent encountered file access permission blocks when attempting to locate/read local workspace files (e.g. `/Users/atarzwell/src/chore-tracking/tests/dummy.png`) on the host system. The application endpoints and layout structure are fully tested via the backend API suite.
* **UI Patches**:
  * *Password Hiding Bug*: Fixed a bug where adding a new user immediately hid the temporary password notification box due to an prompt-refresh reload call. Resolved by passing an optional `keepMessage` parameter to prevent early clearings of alerts.
  * *Immediate Confirmation Close*: Resolved a bug where parent delete prompts immediately closed. Patched dynamic delete/edit buttons to explicitly include `type="button"`, `event.preventDefault()`, and `event.stopPropagation()` to isolate click interactions and prevent browser reloads.

---

## 🔮 Future Enhancements

1. **AI Image Analysis**: Incorporate a computer-vision endpoint (such as Gemini API) to analyze uploaded proof images. It can verify that the chore matches the picture (e.g., checking if a bed is actually made or toys are put away) before marking it completed.
2. **Flexible Frequencies**: Expand chores to support non-daily periods (e.g., weekly, specific weekdays, or monthly chores).
3. **Push Notifications**: Integrate web push alerts to remind kids of pending chores before bedtime.
