import os
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
    children = list(db.users.find({"role": "child"}, {"username": 1, "_id": 0}))
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
    
    db.users.insert_one({
        "username": username,
        "password_hash": hashed,
        "role": "child",
        "is_temp_password": True
    })
    
    return jsonify({
        "status": "success",
        "username": username,
        "password": temp_password
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
