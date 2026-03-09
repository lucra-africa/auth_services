# PostgreSQL Database Interaction Script for Poruta Auth Service
# Run commands one at a time by selecting and pressing F8 in PowerShell ISE or VS Code

# ══════════════════════════════════════════════════════════════════════
# SETUP - Set your database password
# ══════════════════════════════════════════════════════════════════════

$env:PGPASSWORD = "poruta_dev_password"
$PSQL = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
$DB_USER = "poruta"
$DB_NAME = "poruta_auth"
$DB_HOST = "localhost"

# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTION - Execute SQL
# ══════════════════════════════════════════════════════════════════════

function Invoke-SQL {
    param([string]$Query)
    & $PSQL -U $DB_USER -h $DB_HOST -d $DB_NAME -c $Query
}

# ══════════════════════════════════════════════════════════════════════
# DATABASE CONNECTION TEST
# ══════════════════════════════════════════════════════════════════════

# Test connection
Invoke-SQL "SELECT current_database(), current_user, version();"

# ══════════════════════════════════════════════════════════════════════
# VIEW TABLES
# ══════════════════════════════════════════════════════════════════════

# List all tables
Invoke-SQL "\dt"

# Table schemas
Invoke-SQL "\d users"
Invoke-SQL "\d email_verification_tokens"
Invoke-SQL "\d refresh_tokens"
Invoke-SQL "\d password_reset_tokens"
Invoke-SQL "\d invitations"
Invoke-SQL "\d agencies"
Invoke-SQL "\d auth_logs"

# ══════════════════════════════════════════════════════════════════════
# USER QUERIES
# ══════════════════════════════════════════════════════════════════════

# View all users
Invoke-SQL "SELECT id, email, role, is_active, is_email_verified, profile_completed, created_at FROM users ORDER BY created_at DESC;"

# Count users by role
Invoke-SQL "SELECT role, COUNT(*) as count FROM users GROUP BY role;"

# Find user by email
Invoke-SQL "SELECT * FROM users WHERE email = 'admin@poruta.com';"

# View users with profiles
Invoke-SQL "SELECT u.email, u.role, p.first_name, p.last_name, p.company_name FROM users u LEFT JOIN user_profiles p ON u.id = p.user_id;"

# View admin users
Invoke-SQL "SELECT id, email, is_active, is_email_verified, created_at FROM users WHERE role = 'admin';"

# ══════════════════════════════════════════════════════════════════════
# USER MODIFICATIONS
# ══════════════════════════════════════════════════════════════════════

# Mark all users as email verified (for testing)
Invoke-SQL "UPDATE users SET is_email_verified = true; SELECT COUNT(*) as updated_count FROM users WHERE is_email_verified = true;"

# Activate a user
Invoke-SQL "UPDATE users SET is_active = true WHERE email = 'user@example.com';"

# Deactivate a user
Invoke-SQL "UPDATE users SET is_active = false WHERE email = 'user@example.com';"

# Delete a user (careful!)
Invoke-SQL "DELETE FROM users WHERE email = 'test@example.com';"

# ══════════════════════════════════════════════════════════════════════
# AGENCY QUERIES
# ══════════════════════════════════════════════════════════════════════

# View all agencies
Invoke-SQL "SELECT * FROM agencies ORDER BY created_at DESC;"

# View agency with manager
Invoke-SQL "SELECT a.name, a.is_active, u.email as manager_email FROM agencies a LEFT JOIN users u ON a.manager_id = u.id;"

# ══════════════════════════════════════════════════════════════════════
# TOKEN QUERIES
# ══════════════════════════════════════════════════════════════════════

# View active refresh tokens
Invoke-SQL "SELECT rt.id, u.email, rt.created_at, rt.expires_at FROM refresh_tokens rt JOIN users u ON rt.user_id = u.id WHERE rt.revoked_at IS NULL ORDER BY rt.created_at DESC LIMIT 10;"

# Count tokens by user
Invoke-SQL "SELECT u.email, COUNT(rt.id) as token_count FROM users u LEFT JOIN refresh_tokens rt ON u.id = rt.user_id WHERE rt.revoked_at IS NULL GROUP BY u.email;"

# View password reset tokens
Invoke-SQL "SELECT t.id, u.email, t.expires_at, t.used_at FROM password_reset_tokens t JOIN users u ON t.user_id = u.id ORDER BY t.created_at DESC LIMIT 10;"

# ══════════════════════════════════════════════════════════════════════
# INVITATION QUERIES
# ══════════════════════════════════════════════════════════════════════

# View all invitations
Invoke-SQL "SELECT i.id, i.email, i.role, u.email as invited_by, i.accepted_at, i.expires_at FROM invitations i LEFT JOIN users u ON i.invited_by = u.id ORDER BY i.created_at DESC;"

# View pending invitations
Invoke-SQL "SELECT email, role, expires_at FROM invitations WHERE accepted_at IS NULL AND expires_at > NOW();"

# ══════════════════════════════════════════════════════════════════════
# AUTH LOG QUERIES
# ══════════════════════════════════════════════════════════════════════

# Recent auth activity
Invoke-SQL "SELECT action, email, ip_address, created_at FROM auth_logs ORDER BY created_at DESC LIMIT 20;"

# Failed login attempts
Invoke-SQL "SELECT email, ip_address, created_at FROM auth_logs WHERE action = 'failed_login' ORDER BY created_at DESC LIMIT 10;"

# Login history for a user
Invoke-SQL "SELECT action, ip_address, user_agent, created_at FROM auth_logs WHERE email = 'admin@poruta.com' ORDER BY created_at DESC;"

# ══════════════════════════════════════════════════════════════════════
# CLEANUP / MAINTENANCE
# ══════════════════════════════════════════════════════════════════════

# Delete expired tokens
Invoke-SQL "DELETE FROM email_verification_tokens WHERE expires_at < NOW();"
Invoke-SQL "DELETE FROM password_reset_tokens WHERE expires_at < NOW();"
Invoke-SQL "DELETE FROM invitations WHERE expires_at < NOW() AND accepted_at IS NULL;"

# Revoke old refresh tokens (older than 30 days)
Invoke-SQL "UPDATE refresh_tokens SET revoked_at = NOW() WHERE created_at < NOW() - INTERVAL '30 days' AND revoked_at IS NULL;"

# ══════════════════════════════════════════════════════════════════════
# RESET DATABASE (DANGER!)
# ══════════════════════════════════════════════════════════════════════

# Clear all data (use with caution - for development only)
# Invoke-SQL "TRUNCATE auth_logs, invitations, password_reset_tokens, refresh_tokens, email_verification_tokens, user_profiles, users, agencies RESTART IDENTITY CASCADE;"

# ══════════════════════════════════════════════════════════════════════
# CUSTOM QUERIES
# ══════════════════════════════════════════════════════════════════════

# Add your custom queries below:
