# Poruta Auth Service - Quick Reference

## 🗄️ Database Interaction Script

**Location:** `scripts/db-interact.ps1`

This PowerShell script provides one-line commands to interact with the MongoDB database.

### Usage:
1. Open the file in VS Code or PowerShell ISE
2. Select any line you want to run
3. Press F8 (or right-click → Run Selection)

### Available Commands:

```powershell
# Connection test
Invoke-SQL "SELECT current_database(), current_user, version();"

# View all users
Invoke-SQL "SELECT id, email, role, is_active, is_email_verified FROM users;"

# View admin users
Invoke-SQL "SELECT id, email, is_active, created_at FROM users WHERE role = 'ADMIN';"

# Count users by role
Invoke-SQL "SELECT role, COUNT(*) FROM users GROUP BY role;"

# View auth logs
Invoke-SQL "SELECT action, email, ip_address, created_at FROM auth_logs ORDER BY created_at DESC LIMIT 20;"

# And many more...
```

---

## 👤 Admin Account Management

### Current Admin Accounts

✅ **Admin Created:**
- Email: `descartes.tuyishime@poruta.com`
- Password: `Integrity@1234`
- Created: Auto-seeded on server startup

### Creating Additional Admins

**Location:** `scripts/create-admin.ps1`

#### Method 1: CLI (Recommended)
```powershell
cd c:\Users\Admin\OneDrive\Desktop\Poruta\auth_services
$env:PYTHONPATH = (Get-Location).Path

# Interactive (will prompt for password)
python -m src.cli create-admin --email "admin2@poruta.com"

# With password in command
python -m src.cli create-admin --email "admin2@poruta.com" --password "SecurePass123!@#"
```

#### Method 2: Auto-seeding via .env
1. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`
2. Restart the server
3. Admin is created automatically if none exists

### Password Requirements
- At least 12 characters
- One uppercase letter
- One lowercase letter
- One digit
- One special character (!@#$%^&*(),.?":{}|<>)

### Multiple Admins Support
✅ **The system supports unlimited admin accounts**
- Each admin needs a unique email
- Use the CLI to create additional admins
- All admins have full system access

---

## 📧 Email Verification Status

**Status:** ✅ **DISABLED** (for simplified development)

### What Changed:
1. ✅ Signup creates users with `is_email_verified=true`
2. ✅ Login no longer checks email verification
3. ✅ Users can log in immediately after signup
4. ✅ Existing users were updated to verified status

### Documentation:
Full details in: `docs/EMAIL_VERIFICATION_STATUS.md`

---

## 🚀 Starting the Auth Service

```powershell
cd "c:\Users\Admin\OneDrive\Desktop\Poruta\auth_services"
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn src.main:app --host 0.0.0.0 --port 8050 --reload
```

Health check: http://localhost:8050/health
Swagger API docs: http://localhost:8050/docs

---

## 📊 Database Quick Queries (MongoDB)

```powershell
# Using mongosh (MongoDB Shell)
mongosh "mongodb://localhost:27017/poruta_auth"

# View all admins
db.users.find({role: "admin"}, {email: 1, is_active: 1, created_at: 1})

# Count users by role
db.users.aggregate([{$group: {_id: "$role", count: {$sum: 1}}}])

# Recent auth activity
db.auth_logs.find().sort({created_at: -1}).limit(10)
```

---

## 🔐 Database Credentials (MongoDB)

- **Host:** localhost
- **Port:** 27017
- **Database:** poruta_auth
- **Connection:** `mongodb://localhost:27017/poruta_auth`

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `scripts/db-interact.ps1` | One-line database commands |
| `scripts/create-admin.ps1` | Admin account creation |
| `docs/EMAIL_VERIFICATION_STATUS.md` | Email verification info |
| `.env` | Configuration settings |
| `src/cli.py` | Command-line interface |
| `src/services/admin_service.py` | Admin operations |

---

## 🧪 Testing Login

1. **Signup a new account:**
   - Go to http://localhost:9000/signup
   - Enter email, password, select role
   - You'll be redirected to login

2. **Login with account:**
   - Go to http://localhost:9000/login
   - Enter credentials
   - Should log in successfully (no email verification needed)

3. **Login as admin:**
   - Email: `descartes.tuyishime@poruta.com`
   - Password: `Integrity@1234`

---

## 🐛 Troubleshooting

### Admin not created
- Check `.env` has `ADMIN_EMAIL` and `ADMIN_PASSWORD` (no spaces)
- Restart the auth service
- Check logs for "Admin user seeded" message

### Can't connect to database
```powershell
# Test connection
python -c "import asyncio; from motor.motor_asyncio import AsyncIOMotorClient; c = AsyncIOMotorClient('mongodb://localhost:27017'); asyncio.run(c.server_info()); print('Connected OK')"
```

### User can't login
- Check if user exists: Run query in `db-interact.ps1`
- Check if email is verified: Should be `true` for all users
- Check if account is active: Should be `true`

---

## 📝 Notes

- Using MongoDB (Motor async driver) for all data storage
- Email verification is disabled for faster development
- Multiple admins are supported out of the box
- All scripts are Windows PowerShell compatible
