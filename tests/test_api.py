import unittest
import json
import io
import os
import pymongo
from datetime import datetime, timedelta
from app import app, db, generate_random_password

class ChoreTrackerAPITestCase(unittest.TestCase):
    def setUp(self):
        # Set up test Flask application client
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads_test')
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        self.client = app.test_client()
        
        # Clean test collections
        db.users.delete_many({})
        db.chores.delete_many({})
        db.completions.delete_many({})
        
        # Bootstrap default admin
        from app import bootstrap_db
        bootstrap_db()

    def tearDown(self):
        # Clear collections
        db.users.delete_many({})
        db.chores.delete_many({})
        db.completions.delete_many({})
        
        # Remove test upload files
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for f in os.listdir(app.config['UPLOAD_FOLDER']):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f))
            os.rmdir(app.config['UPLOAD_FOLDER'])

    def login_user(self, username, password):
        return self.client.post('/api/auth/login', json={
            "username": username,
            "password": password
        })

    def logout_user(self):
        return self.client.post('/api/auth/logout')

    def test_admin_flow(self):
        # 1. Login with bootstrap admin
        resp = self.login_user("admin", "admin")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['user']['is_temp_password'])
        
        # 2. Force password change
        resp = self.client.post('/api/auth/change-password', json={
            "new_password": "adminnewpass"
        })
        self.assertEqual(resp.status_code, 200)
        
        # 3. Create a parent user
        resp = self.client.post('/api/parents', json={
            "username": "test_parent"
        })
        self.assertEqual(resp.status_code, 201)
        parent_data = json.loads(resp.data)
        self.assertEqual(parent_data['username'], 'test_parent')
        temp_parent_pwd = parent_data['password']
        self.assertIsNotNone(temp_parent_pwd)
        
        # 4. Try to login as parent and change password
        self.logout_user()
        resp = self.login_user("test_parent", temp_parent_pwd)
        self.assertEqual(resp.status_code, 200)
        
        resp = self.client.post('/api/auth/change-password', json={
            "new_password": "parentnewpass"
        })
        self.assertEqual(resp.status_code, 200)

    def test_parent_and_child_flows(self):
        # Seeding a parent directly to skip admin login
        from app import generate_random_password
        import bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(b"parentpass", salt).decode('utf-8')
        db.users.insert_one({
            "username": "jane_parent",
            "password_hash": hashed,
            "role": "parent",
            "is_temp_password": False
        })
        
        # Login parent
        self.login_user("jane_parent", "parentpass")
        
        # 1. Add a child
        resp = self.client.post('/api/children', json={
            "username": "kid_timmy"
        })
        self.assertEqual(resp.status_code, 201)
        child_data = json.loads(resp.data)
        temp_child_pwd = child_data['password']
        
        # 2. Add a chore assigned to Tommy
        resp = self.client.post('/api/chores', json={
            "title": "Clean Room",
            "description": "Vacuum floor and make the bed",
            "assigned_to": "kid_timmy"
        })
        self.assertEqual(resp.status_code, 201)
        chore_id = json.loads(resp.data)['chore']['id']
        
        # 3. Try to add chore for non-existent child (should fail)
        resp = self.client.post('/api/chores', json={
            "title": "Do Dishes",
            "assigned_to": "ghost_kid"
        })
        self.assertEqual(resp.status_code, 400)
        
        # 4. Log in as child
        self.logout_user()
        self.login_user("kid_timmy", temp_child_pwd)
        
        # Force password change for child
        resp = self.client.post('/api/auth/change-password', json={
            "new_password": "kidnewpass"
        })
        self.assertEqual(resp.status_code, 200)
        
        # 5. Retrieve assigned chores
        today_str = datetime.now().strftime("%Y-%m-%d")
        resp = self.client.get(f'/api/chores?date={today_str}')
        self.assertEqual(resp.status_code, 200)
        chores = json.loads(resp.data)
        self.assertEqual(len(chores), 1)
        self.assertEqual(chores[0]['title'], 'Clean Room')
        self.assertFalse(chores[0]['completed'])
        
        # 6. Attempt to mark future chore completed (should fail)
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        dummy_file = (io.BytesIO(b"dummy image data"), 'test.jpg')
        resp = self.client.post('/api/completions', data={
            "chore_id": chore_id,
            "date": tomorrow_str,
            "client_today": today_str,
            "image": dummy_file
        }, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("only be completed on the current day", json.loads(resp.data)['error'])

        # Attempt to mark past chore completed (should fail)
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        dummy_file = (io.BytesIO(b"dummy image data"), 'test.jpg')
        resp = self.client.post('/api/completions', data={
            "chore_id": chore_id,
            "date": yesterday_str,
            "client_today": today_str,
            "image": dummy_file
        }, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("only be completed on the current day", json.loads(resp.data)['error'])

        # 7. Complete today's chore with image (should succeed)
        dummy_file = (io.BytesIO(b"dummy image data"), 'test.jpg')
        resp = self.client.post('/api/completions', data={
            "chore_id": chore_id,
            "date": today_str,
            "client_today": today_str,
            "image": dummy_file
        }, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 201)
        self.assertIn("/static/uploads/", json.loads(resp.data)['image_path'])
        
        # 8. Create a second chore and complete it WITHOUT image (should succeed)
        self.logout_user()
        self.login_user("jane_parent", "parentpass")
        resp = self.client.post('/api/chores', json={
            "title": "Do Dishes",
            "assigned_to": "kid_timmy"
        })
        self.assertEqual(resp.status_code, 201)
        chore_id_2 = json.loads(resp.data)['chore']['id']

        self.logout_user()
        self.login_user("kid_timmy", "kidnewpass")
        resp = self.client.post('/api/completions', data={
            "chore_id": chore_id_2,
            "date": today_str,
            "client_today": today_str
        })
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.data)
        self.assertIsNone(data.get('image_path'))
        
        # Check chores list again -> should show both completed
        resp = self.client.get(f'/api/chores?date={today_str}')
        chores = json.loads(resp.data)
        self.assertEqual(len(chores), 2)
        self.assertTrue(chores[0]['completed'])
        self.assertTrue(chores[1]['completed'])

        # Test Parent changing Child's password
        self.logout_user()
        self.login_user("jane_parent", "parentpass")
        resp = self.client.post('/api/children/kid_timmy/change-password', json={
            "new_password": "timmyresetpass"
        })
        self.assertEqual(resp.status_code, 200)

        # Confirm child can log in and is flagged to change password
        self.logout_user()
        resp = self.login_user("kid_timmy", "timmyresetpass")
        self.assertEqual(resp.status_code, 200)
        user_data = json.loads(resp.data)['user']
        self.assertTrue(user_data['is_temp_password'])

if __name__ == '__main__':
    unittest.main()
