# Auth Service Logging Guide

## ✅ What I Added

I've enhanced the auth service with comprehensive HTTP request/response logging so you can see all API activity in real-time.

## 🔍 Log Features

### 1. **Incoming Request Logs**
Every request shows:
- HTTP method (GET, POST, etc.)
- Request path
- Query parameters (if any)

### 2. **Response Logs**  
After processing, you'll see:
- Status indicator (✓ for success, ✗ for errors)
- HTTP method and path
- Status code (200, 404, 500, etc.)
- Processing time in milliseconds
- Client IP address

### 3. **Startup Logs**
- Database connection status
- Admin user seeding
- Server ready message

## 📝 Example Log Output

```
2026-03-09 08:57:08,637 | INFO     | src.main | Starting Poruta Auth Service
2026-03-09 08:57:08,736 | INFO     | src.main | Auth service ready on port 8050
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8050 (Press CTRL+C to quit)

2026-03-09 09:05:12,123 | INFO     | src.main | → POST /api/auth/register
2026-03-09 09:05:12,145 | INFO     | src.main | ← ✓ POST /api/auth/register [201] 22.45ms (from 192.168.1.100)

2026-03-09 09:05:15,234 | INFO     | src.main | → POST /api/auth/login
2026-03-09 09:05:15,267 | INFO     | src.main | ← ✓ POST /api/auth/login [200] 33.12ms (from 192.168.1.100)

2026-03-09 09:05:20,456 | INFO     | src.main | → GET /api/users/profile
2026-03-09 09:05:20,459 | INFO     | src.main |   Query: {'include': 'agencies'}
2026-03-09 09:05:20,478 | INFO     | src.main | ← ✓ GET /api/users/profile [200] 22.15ms (from 192.168.1.100)

2026-03-09 09:05:25,789 | INFO     | src.main | → GET /api/nonexistent
2026-03-09 09:05:25,791 | INFO     | src.main | ← ✗ GET /api/nonexistent [404] 1.89ms (from 192.168.1.100)
```

## 🚀 How to View Logs

### Option 1: Console (Recommended for Development)

Start the server normally:
```powershell
cd C:\Users\Admin\OneDrive\Desktop\Poruta\auth_services
.\scripts\start-auth.ps1
```

All logs will appear in your terminal window in real-time.

### Option 2: Background with Log Follow

Start in background and tail logs:
```powershell
# Start server in background
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Users\Admin\OneDrive\Desktop\Poruta\auth_services; .\scripts\start-auth.ps1"
```

### Option 3: File Logging (Optional)

If you want to save logs to a file, redirect output:
```powershell
cd C:\Users\Admin\OneDrive\Desktop\Poruta\auth_services
.\scripts\start-auth.ps1 2>&1 | Tee-Object -FilePath "logs\auth-service.log"
```

## 🎯 What You'll See

### Successful Requests (Status 2xx, 3xx)
- Marked with `✓` 
- Shows processing time
- Logs client IP

### Failed Requests (Status 4xx, 5xx)  
- Marked with `✗`
- Shows error status code
- Helps debug issues

### Query Parameters
- Automatically logged when present
- Useful for debugging API calls

## 🔧 Customizing Logs

The logging is configured in [src/main.py](src/main.py). You can adjust:

- **Log level**: Change `logging.INFO` to `logging.DEBUG` for more details
- **Format**: Modify the log format string
- **Middleware**: Add more details to request/response logs

## 📊 Log Levels

Current setup logs at `INFO` level, which includes:
- All HTTP requests/responses
- Database operations (SQLAlchemy)
- Application lifecycle events

For production, consider:
- Setting level to `WARNING` or `ERROR`
- Using structured logging (JSON format)
- Sending logs to a log aggregation service

## 🛠️ Testing the Logs

Try these commands to see the logs in action:

```powershell
# Health check
curl http://localhost:8050/health

# Register a user
curl -X POST http://localhost:8050/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email":"test@example.com","password":"Test123!@#"}'

# Login
curl -X POST http://localhost:8050/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"test@example.com","password":"Test123!@#"}'
```

Each request will show up in your logs with timing and status information!
