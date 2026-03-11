# Create Admin Accounts for Poruta Auth Service
# Run this script to create additional admin users

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

$AUTH_DIR = "c:\Users\Admin\OneDrive\Desktop\Poruta\auth_services"

# Set PYTHONPATH
$env:PYTHONPATH = $AUTH_DIR

# ══════════════════════════════════════════════════════════════════════
# METHOD 1: Create Admin via CLI (Recommended)
# ══════════════════════════════════════════════════════════════════════

# Create admin interactively (will prompt for password)
python -m src.cli create-admin --email "admin@poruta.com"

# Create admin with password in command (less secure)
python -m src.cli create-admin --email "admin@poruta.com" --password "YourSecurePassword123!"

# ══════════════════════════════════════════════════════════════════════
# METHOD 2: Create Multiple Admins (Run one at a time)
# ══════════════════════════════════════════════════════════════════════

# Admin 1
python -m src.cli create-admin --email "admin1@poruta.com" --password "AdminPass123!@#"

# Admin 2
python -m src.cli create-admin --email "admin2@poruta.com" --password "AdminPass456!@#"

# Admin 3
python -m src.cli create-admin --email "admin3@poruta.com" --password "AdminPass789!@#"

# ══════════════════════════════════════════════════════════════════════
# METHOD 3: Check Admin Seeding from .env
# ══════════════════════════════════════════════════════════════════════

# The admin from .env is auto-created on server startup if:
# 1. ADMIN_EMAIL and ADMIN_PASSWORD are set in .env
# 2. No admin users exist in the database

# Restart the server to trigger auto-seeding:
# cd "c:\Users\Admin\OneDrive\Desktop\Poruta\auth_services"
# $env:PYTHONPATH = (Get-Location).Path
# python -m uvicorn src.main:app --host 0.0.0.0 --port 8050 --reload

# ══════════════════════════════════════════════════════════════════════
# VERIFY ADMINS IN DATABASE
# ══════════════════════════════════════════════════════════════════════

$env:PGPASSWORD = "poruta_dev_password"
$PSQL = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

# List all admin users
& $PSQL -U poruta -h localhost -d poruta_auth -c "SELECT id, email, is_active, created_at FROM users WHERE role = 'admin' ORDER BY created_at;"

# Count total admins
& $PSQL -U poruta -h localhost -d poruta_auth -c "SELECT COUNT(*) as admin_count FROM users WHERE role = 'admin';"

# ══════════════════════════════════════════════════════════════════════
# PASSWORD REQUIREMENTS
# ══════════════════════════════════════════════════════════════════════

# Admin passwords must meet these requirements:
# - At least 12 characters
# - One uppercase letter
# - One lowercase letter
# - One digit
# - One special character (!@#$%^&*(),.?":{}|<>)

# ══════════════════════════════════════════════════════════════════════
# TROUBLESHOOTING
# ══════════════════════════════════════════════════════════════════════

# If you get "User already exists", the email is taken
# Check existing users:
& $PSQL -U poruta -h localhost -d poruta_auth -c "SELECT email, role FROM users;"

# If password validation fails, check requirements above

# ══════════════════════════════════════════════════════════════════════
# NOTES
# ══════════════════════════════════════════════════════════════════════

# - Multiple admins are supported out of the box
# - Each admin needs a unique email address
# - Admins have full access to the system
# - Admin accounts are marked as:
#   * is_email_verified = true (no email verification needed)
#   * is_active = true (immediately active)
#   * profile_completed = true (no profile completion needed)
