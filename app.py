import os
import re
import secrets
import string
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, render_template
import pymongo
from bson.objectid import ObjectId
import bcrypt
from werkzeug.utils import secure_filename


app = Flask(__name__, template_folder='templates', static_folder='static')

# Flask configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB file upload limit

# Ensure uploads folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

#print("ROUTER PASSWORD")
#print(os.environ.get("GLINET_ROUTER_PASS", "Not Set"))

# MongoDB connection
mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/chore_tracking")
client = pymongo.MongoClient(mongo_uri)

# Retrieve database reference
try:
    db = client.get_default_database()
except Exception:
    db = client['chore_tracking']

# Set up collection indexes
db.users.create_index("username", unique=True)
db.completions.create_index([("chore_id", 1), ("date", 1), ("completed_by", 1)], unique=True)

# File configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_random_password(length=8) -> str:
    """Generates an alphanumeric temporary password for new accounts."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def normalize_mac(mac: str) -> str:
    """Normalize a MAC address to uppercase colon-separated format (XX:XX:XX:XX:XX:XX)."""
    if not mac:
        return ""
    m = re.sub(r'[^0-9a-fA-F]', '', str(mac))
    if len(m) != 12:
        raise ValueError(f"Invalid MAC address (need 12 hex chars): {mac}")
    return ':'.join(m[i:i+2].upper() for i in range(0, 12, 2))

def bootstrap_db():
    """Bootstraps the default admin account on startup if it doesn't exist."""
    try:
        admin = db.users.find_one({"username": "admin"})
        if not admin:
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(b"admin", salt).decode('utf-8')
            db.users.insert_one({
                "username": "admin",
                "password_hash": hashed,
                "role": "admin",
                "is_temp_password": True
            })
            print("Admin user bootstrapped successfully with username 'admin' and password 'admin'", flush=True)
        else:
            print("Database bootstrap: admin user already exists.", flush=True)
    except Exception as e:
        print(f"Error bootstrapping database: {e}", flush=True)

# Run database bootstrapping
bootstrap_db()

# Decorators for auth
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"error": "Unauthorized. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return jsonify({"error": "Unauthorized. Please log in."}), 401
            user_role = session['user'].get('role')
            if user_role not in roles:
                return jsonify({"error": "Forbidden. Insufficient permissions."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Page Delivery ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Auth APIs ---
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
        
    user = db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401
        
    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({"error": "Invalid username or password"}), 401
        
    session['user'] = {
        "id": str(user['_id']),
        "username": user['username'],
        "role": user['role']
    }
    
    return jsonify({
        "status": "success",
        "user": {
            "username": user['username'],
            "role": user['role'],
            "is_temp_password": user.get('is_temp_password', False)
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"status": "success"})

@app.route('/api/auth/session', methods=['GET'])
def get_session():
    if 'user' in session:
        user = db.users.find_one({"username": session['user']['username']})
        if user:
            return jsonify({
                "logged_in": True,
                "user": {
                    "username": user['username'],
                    "role": user['role'],
                    "is_temp_password": user.get('is_temp_password', False)
                }
            })
    return jsonify({"logged_in": False})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    new_password = data.get('new_password', '')
    
    if not new_password or len(new_password) < 4:
        return jsonify({"error": "Password must be at least 4 characters long"}), 400
        
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    
    db.users.update_one(
        {"username": session['user']['username']},
        {"$set": {"password_hash": hashed, "is_temp_password": False}}
    )
    
    return jsonify({"status": "success", "message": "Password updated successfully"})

# --- Admin APIs (Manage Parents) ---
@app.route('/api/parents', methods=['GET'])
@role_required('admin')
def list_parents():
    parents = list(db.users.find({"role": "parent"}, {"username": 1, "_id": 0}))
    return jsonify(parents)

@app.route('/api/parents', methods=['POST'])
@role_required('admin')
def add_parent():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({"error": "Username is required"}), 400
        
    if db.users.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400
        
    temp_password = generate_random_password()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(temp_password.encode('utf-8'), salt).decode('utf-8')
    
    db.users.insert_one({
        "username": username,
        "password_hash": hashed,
        "role": "parent",
        "is_temp_password": True
    })
    
    return jsonify({
        "status": "success",
        "username": username,
        "password": temp_password
    }), 201

@app.route('/api/parents/<username>', methods=['DELETE'])
@role_required('admin')
def delete_parent(username):
    result = db.users.delete_one({"username": username, "role": "parent"})
    if result.deleted_count == 0:
        return jsonify({"error": "Parent not found"}), 404
        
    return jsonify({"status": "success", "message": f"Parent {username} removed successfully"})

# --- Parent APIs (Manage Children & Chores) ---
@app.route('/api/children', methods=['GET'])
@role_required('parent')
def list_children():
    children = []
    for doc in db.users.find({"role": "child"}, {"username": 1, "mac_addresses": 1, "_id": 0}):
        children.append({
            "username": doc["username"],
            "mac_addresses": doc.get("mac_addresses", [])
        })
    return jsonify(children)

@app.route('/api/children', methods=['POST'])
@role_required('parent')
def add_child():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({"error": "Username is required"}), 400
        
    if db.users.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400
        
    temp_password = generate_random_password()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(temp_password.encode('utf-8'), salt).decode('utf-8')
    
    # Handle optional initial MAC addresses (array or newline/comma string)
    raw_macs = data.get('mac_addresses', [])
    if isinstance(raw_macs, str):
        # Support comma or newline separated from forms
        raw_macs = [line.strip() for line in raw_macs.replace(',', '\n').split('\n')]
    
    mac_addresses = []
    for m in raw_macs:
        if m and str(m).strip():
            try:
                normalized = normalize_mac(m)
                if normalized and normalized not in mac_addresses:
                    mac_addresses.append(normalized)
            except ValueError:
                # Skip invalid; could also return error. For UX, be lenient on initial add.
                pass
    
    user_doc = {
        "username": username,
        "password_hash": hashed,
        "role": "child",
        "is_temp_password": True,
        "mac_addresses": mac_addresses
    }
    
    db.users.insert_one(user_doc)
    
    return jsonify({
        "status": "success",
        "username": username,
        "password": temp_password,
        "mac_addresses": mac_addresses
    }), 201

@app.route('/api/children/<username>', methods=['DELETE'])
@role_required('parent')
def delete_child(username):
    result = db.users.delete_one({"username": username, "role": "child"})
    if result.deleted_count == 0:
        return jsonify({"error": "Child not found"}), 404
        
    # Clean up completions and chores for this child
    db.completions.delete_many({"completed_by": username})
    db.chores.delete_many({"assigned_to": username})
    
    return jsonify({"status": "success", "message": f"Child {username} removed successfully"})

@app.route('/api/children/<username>/change-password', methods=['POST'])
@role_required('parent')
def change_child_password(username):
    child = db.users.find_one({"username": username, "role": "child"})
    if not child:
        return jsonify({"error": "Child not found"}), 404
        
    data = request.get_json() or {}
    new_password = data.get('new_password', '')
    
    if not new_password or len(new_password) < 4:
        return jsonify({"error": "Password must be at least 4 characters long"}), 400
        
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    
    db.users.update_one(
        {"username": username, "role": "child"},
        {"$set": {"password_hash": hashed, "is_temp_password": True}}
    )
    
    return jsonify({"status": "success", "message": f"Password for child {username} updated successfully"})


# --- Parent: Child MAC Address Management (for GL.iNet router integration) ---
@app.route('/api/children/<username>/mac-addresses', methods=['GET'])
@role_required('parent')
def get_child_mac_addresses(username):
    child = db.users.find_one({"username": username, "role": "child"}, {"username": 1, "mac_addresses": 1, "_id": 0})
    if not child:
        return jsonify({"error": "Child not found"}), 404
    return jsonify({
        "username": child["username"],
        "mac_addresses": child.get("mac_addresses", [])
    })


@app.route('/api/children/<username>/mac-addresses', methods=['PUT'])
@role_required('parent')
def update_child_mac_addresses(username):
    child = db.users.find_one({"username": username, "role": "child"})
    if not child:
        return jsonify({"error": "Child not found"}), 404
    
    data = request.get_json() or {}
    raw_macs = data.get('mac_addresses', [])
    
    if not isinstance(raw_macs, list):
        return jsonify({"error": "mac_addresses must be a list"}), 400
    
    mac_addresses = []
    errors = []
    for m in raw_macs:
        if m and str(m).strip():
            try:
                normalized = normalize_mac(m)
                if normalized and normalized not in mac_addresses:
                    mac_addresses.append(normalized)
            except ValueError as e:
                errors.append(str(e))
    
    if errors:
        # Still allow partial success, but report issues
        pass
    
    db.users.update_one(
        {"username": username, "role": "child"},
        {"$set": {"mac_addresses": mac_addresses}}
    )
    
    return jsonify({
        "status": "success",
        "username": username,
        "mac_addresses": mac_addresses,
        "invalid": errors if errors else None
    })


# --- Parent Manual Router Controls + Refresh + Logs ---

@app.route('/api/children/<username>/router/block', methods=['POST'])
@role_required('parent')
def block_child_internet(username):
    """Manually add the child's MACs to the blacklist (restrict internet)."""
    actor = session['user']['username']
    success, msg = _add_child_to_blacklist(username, actor=actor)
    if success:
        return jsonify({"status": "success", "message": f"Internet blocked for {username}."})
    else:
        return jsonify({"status": "error", "message": msg or "Failed to block internet."}), 500


@app.route('/api/children/<username>/router/allow', methods=['POST'])
@role_required('parent')
def allow_child_internet(username):
    """Manually remove the child's MACs from the blacklist (allow internet)."""
    actor = session['user']['username']
    success, msg = _remove_child_from_blacklist(username, actor=actor)
    if success:
        return jsonify({"status": "success", "message": f"Internet allowed for {username}."})
    else:
        return jsonify({"status": "error", "message": msg or "Failed to allow internet."}), 500


@app.route('/api/router/refresh', methods=['POST'])
@role_required('parent')
def refresh_router_status():
    """
    Parent-triggered "Refresh Router Status".

    Computes the correct blacklist state for *today* based on actual chore completion:
      - Any child who has NOT completed all their chores for today → their MAC addresses must be in the blacklist.
      - Any child who HAS completed all their chores for today (or has no chores assigned) → their MAC addresses must NOT be in the blacklist.

    Fetches the current blacklist from the router (initial),
    determines the required adds/removes,
    applies them via the GL.iNet client (updating flags and logging each action),
    then returns the initial list, the changes that were applied, and the final list from the router.
    """
    actor = session['user']['username']
    client = _get_router_client()
    if not client:
        return jsonify({"error": "Router client not available. Check GLINET_ROUTER_PASS / GLINET_HOST."}), 503

    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Initial blacklist from the router
        lists = client.get_lists()
        initial_black = sorted(set(lists.get('black', []) or []))

        # Load children
        children = list(db.users.find(
            {"role": "child"},
            {"username": 1, "mac_addresses": 1}
        ))

        changes_to_block = []
        changes_to_unblock = []

        for child in children:
            username = child["username"]
            macs = child.get("mac_addresses", []) or []
            if not macs:
                continue

            chores = list(db.chores.find({"assigned_to": username}))
            if not chores:
                # No chores assigned today → should be allowed (not blacklisted)
                for mac in macs:
                    if mac in initial_black:
                        changes_to_unblock.append({"mac": mac, "child": username})
                continue

            completed_count = db.completions.count_documents({
                "completed_by": username,
                "date": today
            })
            all_completed = completed_count >= len(chores)

            for mac in macs:
                currently_blocked = mac in initial_black
                if not all_completed and not currently_blocked:
                    # Must be blocked
                    changes_to_block.append({"mac": mac, "child": username})
                elif all_completed and currently_blocked:
                    # Must be unblocked
                    changes_to_unblock.append({"mac": mac, "child": username})

        # Apply the required changes.
        # The helper functions will update the child's router_blacklisted flag
        # and create detailed log entries.
        for item in changes_to_block:
            _add_child_to_blacklist(item["child"], actor=f"{actor} (refresh)")

        for item in changes_to_unblock:
            _remove_child_from_blacklist(item["child"], actor=f"{actor} (refresh)")

        # Resultant blacklist from the router after our changes
        final_lists = client.get_lists()
        resultant_black = sorted(set(final_lists.get('black', []) or []))

        return jsonify({
            "status": "success",
            "today": today,
            "initial_blacklist": initial_black,
            "changes": {
                "to_block": changes_to_block,
                "to_unblock": changes_to_unblock
            },
            "resultant_blacklist": resultant_black,
            "message": f"Refresh complete for {today}. {len(changes_to_block)} MAC(s) added to blacklist, {len(changes_to_unblock)} removed."
        })

    except Exception as e:
        return jsonify({"error": f"Router refresh failed: {str(e)}"}), 500


@app.route('/api/router/logs', methods=['GET'])
@role_required('parent')
def get_router_logs():
    """Return recent router actions for visibility."""
    try:
        logs = list(
            db.router_logs.find({}, {"_id": 0})
            .sort("timestamp", pymongo.DESCENDING)
            .limit(100)
        )
        # Convert datetimes to ISO for JSON
        for log in logs:
            if "timestamp" in log and hasattr(log["timestamp"], "isoformat"):
                log["timestamp"] = log["timestamp"].isoformat()
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- GL.iNet Router Integration Helpers (blacklist control for children) ---

def _get_router_client():
    """Return a configured GlinetClient or None if router integration is not available."""
    try:
        import glinet_blacklist as glib
        host = os.environ.get("GLINET_HOST", "192.168.8.1")
        # Password is automatically picked up from GLINET_ROUTER_PASS (injected via Docker secret)
        return glib.GlinetClient(host=host)
    except Exception as e:
        print(f"[router] Could not initialize GlinetClient: {e}", flush=True)
        return None


def _log_router_action(action, child_username, macs, actor, success, error=None, date=None):
    """Insert a record of a router blacklist operation."""
    try:
        db.router_logs.insert_one({
            "timestamp": datetime.utcnow(),
            "action": action,  # "add_to_blacklist" or "remove_from_blacklist"
            "child_username": child_username,
            "mac_addresses": macs or [],
            "actor": actor,  # parent username, "auto_completion", "daily_reset", etc.
            "success": bool(success),
            "error": error,
            "date": date
        })
    except Exception as log_err:
        print(f"[router] Failed to log action: {log_err}", flush=True)


def _execute_router_action(child_username, action, actor, date=None):
    """
    Perform add_to_blacklist or remove_from_blacklist for a child's MACs.
    Updates the child's router_blacklisted flag and logs the action.
    Returns (success, message)
    """
    child = db.users.find_one({"username": child_username, "role": "child"})
    if not child:
        return False, "Child not found"

    macs = child.get("mac_addresses", [])
    if not macs:
        new_blacklisted = (action == "add_to_blacklist")
        db.users.update_one(
            {"username": child_username, "role": "child"},
            {"$set": {"router_blacklisted": new_blacklisted}}
        )
        _log_router_action(action, child_username, [], actor, True, "No MAC addresses configured", date)
        return True, "No MAC addresses configured for child"

    client = _get_router_client()
    overall_success = True
    error_details = None

    if client:
        for mac in macs:
            try:
                if action == "add_to_blacklist":
                    client.add_to_blacklist(mac)
                else:
                    client.remove_from_blacklist(mac)
            except Exception as e:
                overall_success = False
                error_details = str(e)
                print(f"[router] {action} failed for {mac} ({child_username}): {e}", flush=True)
    else:
        overall_success = False
        error_details = "Router client not available (check GLINET_ROUTER_PASS / GLINET_HOST)"

    new_blacklisted = (action == "add_to_blacklist")
    db.users.update_one(
        {"username": child_username, "role": "child"},
        {"$set": {"router_blacklisted": new_blacklisted}}
    )

    _log_router_action(action, child_username, macs, actor, overall_success, error_details, date)

    return overall_success, error_details or "Success"


def _add_child_to_blacklist(username, actor="system", date=None):
    """Add all of a specific child's MAC addresses to the blacklist (restricts internet)."""
    return _execute_router_action(username, "add_to_blacklist", actor, date)


def _remove_child_from_blacklist(username, actor="system", date=None):
    """Remove all of a specific child's MAC addresses from the blacklist (allows internet)."""
    return _execute_router_action(username, "remove_from_blacklist", actor, date)


def daily_blacklist_reset():
    """Scheduled job: at 4am local time, add ALL children's MACs back to the blacklist."""
    print("[router] Running daily 4am blacklist reset for all children...", flush=True)
    try:
        children = list(db.users.find({"role": "child"}, {"username": 1}))
        for child in children:
            _add_child_to_blacklist(child["username"], actor="daily_reset")
        print("[router] Daily 4am blacklist reset complete.", flush=True)
    except Exception as e:
        print(f"[router] Daily blacklist reset error: {e}", flush=True)


def check_and_manage_blacklist_on_completion(username: str, date_str: str):
    """Called after a child completes a chore.

    If this child has now completed *all* of their assigned chores for the given date,
    remove their MAC addresses from the router blacklist (lift internet restriction).
    """
    try:
        child = db.users.find_one({"username": username, "role": "child"})
        if not child:
            return
        macs = child.get("mac_addresses", [])
        if not macs:
            return

        # Get all chores currently assigned to this child
        chores = list(db.chores.find({"assigned_to": username}))
        if not chores:
            # No chores assigned — consider "all done" and allow access
            _remove_child_from_blacklist(username, actor="auto_completion", date=date_str)
            return

        # Check completion status for every chore on this specific date
        all_done = True
        for chore in chores:
            comp = db.completions.find_one({
                "chore_id": chore["_id"],
                "date": date_str,
                "completed_by": username
            })
            if not comp:
                all_done = False
                break

        if all_done:
            _remove_child_from_blacklist(username, actor="auto_completion", date=date_str)
    except Exception as e:
        print(f"[router] Error in completion blacklist check for {username} on {date_str}: {e}", flush=True)


# --- Chore APIs ---
@app.route('/api/chores', methods=['GET'])
@login_required
def list_chores():
    user_role = session['user']['role']
    username = session['user']['username']
    date_param = request.args.get('date')  # YYYY-MM-DD
    
    query = {}
    if user_role == 'child':
        query['assigned_to'] = username
    
    chores = list(db.chores.find(query))
    
    formatted_chores = []
    for chore in chores:
        chore_id_str = str(chore['_id'])
        c_doc = {
            "id": chore_id_str,
            "title": chore['title'],
            "description": chore.get('description', ''),
            "assigned_to": chore['assigned_to'],
            "completed": False,
            "image_path": None,
            "completed_at": None
        }
        
        if date_param:
            completion = db.completions.find_one({
                "chore_id": ObjectId(chore_id_str),
                "date": date_param
            })
            if completion:
                c_doc["completed"] = True
                c_doc["image_path"] = completion.get("image_path")
                c_doc["completed_at"] = completion.get("completed_at").isoformat() if completion.get("completed_at") else None
                
        formatted_chores.append(c_doc)
        
    return jsonify(formatted_chores)

@app.route('/api/chores', methods=['POST'])
@role_required('parent')
def create_chore():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    assigned_to = data.get('assigned_to', '').strip()
    
    if not title or not assigned_to:
        return jsonify({"error": "Title and Assigned To child are required"}), 400
        
    child = db.users.find_one({"username": assigned_to, "role": "child"})
    if not child:
        return jsonify({"error": f"Child user '{assigned_to}' does not exist"}), 400
        
    chore_doc = {
        "title": title,
        "description": description,
        "assigned_to": assigned_to,
        "created_at": datetime.utcnow()
    }
    
    result = db.chores.insert_one(chore_doc)
    chore_doc['id'] = str(result.inserted_id)
    del chore_doc['_id']
    del chore_doc['created_at']
    
    return jsonify({"status": "success", "chore": chore_doc}), 201

@app.route('/api/chores/<chore_id>', methods=['PUT'])
@role_required('parent')
def update_chore(chore_id):
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    assigned_to = data.get('assigned_to', '').strip()
    
    if not title or not assigned_to:
        return jsonify({"error": "Title and Assigned To child are required"}), 400
        
    child = db.users.find_one({"username": assigned_to, "role": "child"})
    if not child:
        return jsonify({"error": f"Child user '{assigned_to}' does not exist"}), 400
        
    try:
        oid = ObjectId(chore_id)
    except Exception:
        return jsonify({"error": "Invalid chore ID format"}), 400
        
    result = db.chores.update_one(
        {"_id": oid},
        {"$set": {
            "title": title,
            "description": description,
            "assigned_to": assigned_to
        }}
    )
    
    if result.matched_count == 0:
        return jsonify({"error": "Chore not found"}), 404
        
    return jsonify({"status": "success", "message": "Chore updated successfully"})

@app.route('/api/chores/<chore_id>', methods=['DELETE'])
@role_required('parent')
def delete_chore(chore_id):
    try:
        oid = ObjectId(chore_id)
    except Exception:
        return jsonify({"error": "Invalid chore ID format"}), 400
        
    result = db.chores.delete_one({"_id": oid})
    if result.deleted_count == 0:
        return jsonify({"error": "Chore not found"}), 404
        
    # Clean up completion records for this chore
    db.completions.delete_many({"chore_id": oid})
    
    return jsonify({"status": "success", "message": "Chore deleted successfully"})

# --- Completion APIs ---
@app.route('/api/completions', methods=['POST'])
@role_required('child')
def complete_chore():
    # Retrieve form-data
    chore_id_str = request.form.get('chore_id')
    date_str = request.form.get('date')  # YYYY-MM-DD
    client_today = request.form.get('client_today')  # YYYY-MM-DD client local date
    
    if not chore_id_str or not date_str or not client_today:
        return jsonify({"error": "Chore ID, date, and client_today parameters are required"}), 400
        
    try:
        chore_id = ObjectId(chore_id_str)
    except Exception:
        return jsonify({"error": "Invalid chore ID format"}), 400
        
    # Verify chore exists and is assigned to the current user
    chore = db.chores.find_one({"_id": chore_id, "assigned_to": session['user']['username']})
    if not chore:
        return jsonify({"error": "Chore not found or not assigned to you"}), 404
        
    # Strictly check date to prevent past or future dates completion
    if date_str != client_today:
        return jsonify({"error": "Chores can only be completed on the current day"}), 400
        
    # Handle optional image upload
    relative_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            if not allowed_file(file.filename):
                return jsonify({"error": "Allowed image formats: PNG, JPG, JPEG, GIF, WEBP"}), 400
                
            # Save image with secure unique name
            ext = file.filename.rsplit('.', 1)[1].lower()
            random_hex = secrets.token_hex(8)
            filename = f"{random_hex}_{int(datetime.utcnow().timestamp())}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            relative_path = f"/static/uploads/{filename}"
    
    try:
        db.completions.insert_one({
            "chore_id": chore_id,
            "date": date_str,
            "completed_by": session['user']['username'],
            "image_path": relative_path,
            "completed_at": datetime.utcnow()
        })
    except pymongo.errors.DuplicateKeyError:
        # Clean up the file if duplicate
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": "Chore already completed for this date"}), 400
        
    # Router / GL.iNet integration:
    # If the child has now completed every one of their chores for this date,
    # remove their devices from the blacklist so they can access the internet.
    try:
        check_and_manage_blacklist_on_completion(
            session['user']['username'], date_str
        )
    except Exception as e:
        print(f"[router] Post-completion blacklist check failed: {e}", flush=True)

    return jsonify({
        "status": "success",
        "message": "Chore marked as completed successfully",
        "image_path": relative_path
    }), 201

@app.route('/api/completions', methods=['GET'])
@login_required
def get_completions():
    user_role = session['user']['role']
    username = session['user']['username']
    start_date = request.args.get('start_date')  # YYYY-MM-DD
    end_date = request.args.get('end_date')  # YYYY-MM-DD
    
    query = {}
    if user_role == 'child':
        query['completed_by'] = username
        
    if start_date or end_date:
        query['date'] = {}
        if start_date:
            query['date']['$gte'] = start_date
        if end_date:
            query['date']['$lte'] = end_date
            
    completions = list(db.completions.find(query))
    
    formatted = []
    for comp in completions:
        chore = db.chores.find_one({"_id": comp['chore_id']})
        formatted.append({
            "id": str(comp['_id']),
            "chore_id": str(comp['chore_id']),
            "chore_title": chore['title'] if chore else "Deleted Chore",
            "chore_description": chore.get('description', '') if chore else "",
            "date": comp['date'],
            "completed_by": comp['completed_by'],
            "image_path": comp['image_path'],
            "completed_at": comp['completed_at'].isoformat() if comp.get('completed_at') else None
        })
        
    return jsonify(formatted)

# --- Daily Router Blacklist Scheduler (4am local/container time) ---
# This starts a background APScheduler job that re-adds every child's MAC addresses
# to the GL.iNet blacklist every day at 4:00 AM according to the container's local time.
# The container timezone can be controlled via the TZ environment variable in docker-compose.
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _blacklist_scheduler = BackgroundScheduler()
    _blacklist_scheduler.add_job(
        daily_blacklist_reset,
        trigger=CronTrigger(hour=4, minute=0),
        id="daily_child_mac_blacklist_reset",
        name="4am daily re-apply blacklist to all children's devices",
        replace_existing=True,
        coalesce=True,
        max_instances=1
    )
    _blacklist_scheduler.start()
    print("[router] 4am daily blacklist reset scheduler started (hour=4 local time).", flush=True)
except Exception as e:
    print(f"[router] Scheduler not started (APScheduler may be missing or another issue): {e}", flush=True)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
