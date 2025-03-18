from flask import Flask, render_template, request, redirect, session, jsonify, url_for, send_from_directory
from flask_cors import CORS
import json
import sqlite3
import os
import sys
import traceback
import time  

app = Flask(__name__)
app.secret_key = "12345"  


CORS(app, resources={r"/*": {"origins": "*"}})


DEFAULT_CREDENTIALS = {
    "admin": "admin123",  
    "test": "test123",    
    "demo": "demo123"     
}

# Initialise database
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    
    # Create users table with email field (if not exists)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT UNIQUE
        )
    """)
    
    # Add profiles table with sensitive information
    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            credit_card TEXT,
            address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Add default users if they don't exist
    for username, password in DEFAULT_CREDENTIALS.items():
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        if not c.fetchone():
            # Add email for each default user
            email = f"{username}@example.com"
            c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                     (username, password, email))
    
    conn.commit()
    conn.close()

# Load pizza data
def load_pizzas():
    try:
        with open("pizza.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# Save pizza data
def save_pizzas(pizzas):
    # Ensure backup directory exists
    os.makedirs("static/backup", exist_ok=True)
    
    # Save to both main file and backup
    with open("pizza.json", "w") as f:
        json.dump(pizzas, f, indent=4)
    
    with open("static/backup/pizza.json.bak", "w") as f:
        json.dump(pizzas, f, indent=4)

# Vulnerable download route for directory traversal
@app.route("/download")
def download():
    filename = request.args.get("file")
    with open(filename, "r") as file:
        return file.read()

# Verbose error route
@app.route("/error_test")
def error_test():
    username = request.args.get("username")
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}'"
    c.execute(query)  
    return f"Executed query: {query}"

# Unrestricted file upload
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files["file"]
        file.save(f"./uploads/{file.filename}")
        return "File uploaded!"
    return '''
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file">
        <button type="submit">Upload</button>
    </form>
    '''

@app.route("/")
def index():
    pizzas = load_pizzas()
    return render_template("index.html", pizzas=pizzas)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Try default credentials first
        if username in DEFAULT_CREDENTIALS and DEFAULT_CREDENTIALS[username] == password:
            session['user'] = username
            return redirect(url_for('index'))

        # If not default, check database
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        c.execute(query)
        user = c.fetchone()
        conn.close()

        if user:
            session['user'] = user[1]  
            return redirect(url_for('index'))
        else:
            return "Invalid credentials! <a href='/'>Try again</a>"

    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "GET":
        return render_template("register.html")
    
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))

@app.route("/reset", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        username = request.form["username"]
        token = request.form["token"]
        if reset_tokens.get(username) == token:
            return "Password reset successful!"
    return render_template("reset.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    pizza_name = request.form.get("pizza_name")
    pizzas = load_pizzas()
    pizza = next((p for p in pizzas if p["name"] == pizza_name), None)
    
    if pizza:
        cart_item = {
            "name": pizza["name"],
            "description": pizza["description"],
            "image": pizza["image"],
            "price": pizza["price"],
            "quantity": 1
        }
        
        if 'cart' not in session:
            session['cart'] = []
        
        existing_item = next((item for item in session['cart'] if item["name"] == pizza_name), None)
        if existing_item:
            existing_item["quantity"] += 1
        else:
            session['cart'].append(cart_item)
        
        session.modified = True
        return redirect(url_for('cart'))
    
    return "Pizza not found!", 404

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "user" not in session or session["user"] != "admin":
        return "Access Denied! <a href='/'>Go back</a>"

    pizzas = load_pizzas()

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        price = float(request.form.get("price", 0))  
        image_file = request.files.get("image")

        if image_file:
            image_filename = f"static/images/{image_file.filename}"
            image_file.save(image_filename)
        else:
            image_filename = None

        if "update" in request.form:
            pizza_id = int(request.form["update"])
            pizzas[pizza_id]["name"] = name
            pizzas[pizza_id]["description"] = description
            pizzas[pizza_id]["price"] = price  
            if image_filename:
                pizzas[pizza_id]["image"] = image_filename
        elif "delete" in request.form:
            pizza_id = int(request.form["delete"])
            if 0 <= pizza_id < len(pizzas):  
                pizzas.pop(pizza_id)
                save_pizzas(pizzas)
                return redirect("/admin")
        else:
            pizzas.append({
                "name": name,
                "description": description,
                "price": price,  
                "image": image_filename
            })

        save_pizzas(pizzas)
        return redirect("/admin")

    return render_template("admin.html", pizzas=pizzas)


@app.route("/cart")
def cart():
    cart_items = session.get('cart', [])
    return render_template("cart.html", cart_items=cart_items)

@app.route("/update_cart", methods=["POST"])
def update_cart():
    item_name = request.form.get("item")
    quantity = request.form.get("quantity")
    
    if 'cart' in session:
        for item in session['cart']:
            if item["name"] == item_name:
                item["quantity"] = int(quantity)
                session.modified = True
                break
    
    return "Updated", 200

@app.route("/remove_from_cart", methods=["POST"])
def remove_from_cart():
    item_name = request.form.get("item")
    
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] if item["name"] != item_name]
        session.modified = True
    
    return "Removed", 200

@app.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")

@app.route("/user/<username>")
def get_user(username):
    try:
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        query = f"SELECT * FROM users WHERE username = '{username}'"
        c.execute(query)  
        user = c.fetchone()
        conn.close()
        
        if user:
            return f"Found user: {user}"
        return "User not found"
    except Exception as e:
        return f"""
            <h2>Database Error</h2>
            <p>Query: {query}</p>
            <p>Error: {str(e)}</p>
        """, 500

@app.route("/debug/<path:file_path>")
def debug_file(file_path):
    try:
        import platform
        system_info = {
            'os': platform.system(),
            'version': platform.version(),
            'python': sys.version,
            'user': os.getlogin(),
            'cwd': os.getcwd(),
            'env': dict(os.environ)
        }
        
        with open(file_path, 'r') as f:
            content = f.read()
            
        return f"""
            <h2>File Content</h2>
            <pre>{content}</pre>
            <h3>System Information</h3>
            <pre>{json.dumps(system_info, indent=2)}</pre>
        """
    except Exception as e:
        return f"""
            <h2>Error Reading File</h2>
            <p>Path: {file_path}</p>
            <p>Error: {str(e)}</p>
            <h3>System Information</h3>
            <pre>{json.dumps(system_info, indent=2)}</pre>
        """, 500

@app.errorhandler(500)
def internal_error(error):
    import traceback
    error_details = {
        'error_type': str(type(error).__name__),
        'error_message': str(error),
        'stack_trace': traceback.format_exc(),
        'python_version': sys.version,
        'flask_version': Flask.__version__,
        'debug_mode': app.debug,
        'database_path': 'users.db'
    }
    return f"""
        <h1>Internal Server Error</h1>
        <pre>
        Error Type: {error_details['error_type']}
        Message: {error_details['error_message']}
        
        Full Stack Trace:
        {error_details['stack_trace']}
        
        System Information:
        Python Version: {error_details['python_version']}
        Flask Version: {error_details['flask_version']}
        Debug Mode: {error_details['debug_mode']}
        Database: {error_details['database_path']}
        </pre>
    """, 500

@app.errorhandler(404)
def page_not_found(e):
    error_message = """
    Page not found. Please check our documentation for valid URLs.
    """
    return error_message, 404

@app.route("/profile/<int:user_id>")
def view_profile(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    
    c.execute("""
        SELECT u.username, p.* 
        FROM users u 
        LEFT JOIN profiles p ON u.id = p.user_id 
        WHERE u.id = ?
    """, (user_id,))
    
    data = c.fetchone()
    conn.close()
    
    if data:
        return f"""
            <h2>User Profile</h2>
            <pre>
            Username: {data[0]}
            Full Name: {data[2]}
            Email: {data[3]}
            Phone: {data[4]}
            Credit Card: {data[5]}
            Address: {data[6]}
            </pre>
            <p><a href="/profile/{user_id - 1}">Previous User</a> | 
               <a href="/profile/{user_id + 1}">Next User</a></p>
        """
    return "Profile not found", 404

@app.route("/create_profile", methods=["GET", "POST"])
def create_profile():
    if request.method == "POST":
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username = ?", (session.get('user'),))
        user = c.fetchone()
        
        if user:
            c.execute("""
                INSERT OR REPLACE INTO profiles 
                (user_id, full_name, email, phone, credit_card, address)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user[0],
                request.form.get('full_name', 'John Doe'),
                request.form.get('email', 'john@example.com'),
                request.form.get('phone', '123-456-7890'),
                request.form.get('credit_card', '4111-1111-1111-1111'),
                request.form.get('address', '123 Main St, City, Country')
            ))
            conn.commit()
            conn.close()
            return redirect(f"/profile/{user[0]}")
            
    return """
        <h2>Create Profile</h2>
        <form method="POST">
            <p>Full Name: <input name="full_name" value="John Doe"></p>
            <p>Email: <input name="email" value="john@example.com"></p>
            <p>Phone: <input name="phone" value="123-456-7890"></p>
            <p>Credit Card: <input name="credit_card" value="4111-1111-1111-1111"></p>
            <p>Address: <input name="address" value="123 Main St, City, Country"></p>
            <p><input type="submit" value="Create Profile"></p>
        </form>
    """

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        
        timestamp = int(time.time())
        token = f"{username}_{timestamp}"  
        
        reset_link = f"http://127.0.0.1:5000/password-reset?username={username}&token={token}"
        
        return f"""
            <h2>Password Reset Requested</h2>
            <p>A password reset link has been generated.</p>
            <p>Normally this would be emailed, but for testing, here's the link:</p>
            <p><a href="{reset_link}">{reset_link}</a></p>
            <p><a href="/">Back to login</a></p>
        """
    
    return """
        <h2>Forgot Password</h2>
        <form method="POST">
            <p>Username: <input type="text" name="username" required></p>
            <p><input type="submit" value="Reset Password"></p>
        </form>
    """

@app.route("/password-reset", methods=["GET", "POST"])
def password_reset():
    username = request.args.get("username") or request.form.get("username")
    token = request.args.get("token") or request.form.get("token")
    
    if not username or not token:
        return "Missing username or token", 400
    
    if request.method == "POST":
        new_password = request.form.get("new_password")
        if not new_password:
            return "Missing new password", 400
        
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        query = f"UPDATE users SET password = '{new_password}' WHERE username = '{username}'"
        c.execute(query)
        conn.commit()
        conn.close()
        
        return """
            <h2>Password Updated</h2>
            <p>Your password has been updated successfully.</p>
            <p><a href="/">Login with new password</a></p>
        """
    
    return f"""
        <h2>Reset Password</h2>
        <form method="POST">
            <input type="hidden" name="username" value="{username}">
            <input type="hidden" name="token" value="{token}">
            <p>New Password: <input type="password" name="new_password" required></p>
            <p><input type="submit" value="Update Password"></p>
        </form>
    """

@app.route('/uploads/<path:filename>')
def serve_file(filename):
    return send_from_directory('uploads', filename)

if __name__ == "__main__":
    if not os.path.exists("uploads"):
        os.mkdir("uploads")
    
    if not os.path.exists("pizza.json"):
        save_pizzas([])  
    
    init_db()
    app.run(debug=True)
