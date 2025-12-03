# Production Deployment Guide - Session Authentication

This guide covers deploying the session-based authentication system to production.

## Pre-Deployment Checklist

### 1. Database Migration

**Run the users table migration on production database:**

```sql
-- Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL;

-- Create trigger function if it doesn't exist
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Or use the schema file:**
```bash
# Connect to production database and run the users table section from schema.sql
psql $DATABASE_URL -f app/database/schema.sql
```

### 2. Environment Variables

**Required for Production:**

```bash
# Session secret key (REQUIRED - minimum 32 characters)
# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
SESSION_SECRET_KEY=your-very-secure-random-secret-key-minimum-32-characters

# Session security (REQUIRED for HTTPS)
SESSION_SECURE=true  # Set to true when using HTTPS

# Environment detection (optional but recommended)
ENVIRONMENT=production
```

**For Aptible Deployment:**

```bash
aptible config:set \
  SESSION_SECRET_KEY=your-generated-secret-key-here \
  SESSION_SECURE=true \
  ENVIRONMENT=production \
  --app your-app-name
```

### 3. Create Initial Admin User

**On production server or via tunnel:**

```bash
# Via Aptible tunnel
aptible db:tunnel your-app-name
# In another terminal:
python3 scripts/create_user.py --username admin --password your-secure-password
```

**Or directly via database:**

```sql
-- You'll need to hash the password first using Python:
-- python3 -c "from app.utils.user_auth import get_password_hash; print(get_password_hash('your-password'))"

INSERT INTO users (username, email, password_hash, is_active)
VALUES ('admin', 'admin@example.com', '$2b$12$...hashed_password...', TRUE);
```

### 4. Dependencies

Ensure `itsdangerous>=2.1.2` is in `requirements.txt` (already added).

## Deployment Steps

### Step 1: Verify Code Changes

```bash
# Check what files changed
git status

# Review changes
git diff
```

### Step 2: Commit Changes

```bash
git add app/api/auth_routes.py
git add app/api/routes.py
git add app/utils/user_auth.py
git add app/templates/login.html
git add app/templates/patients_table.html
git add app/database/schema.sql
git add requirements.txt
git add scripts/create_user.py

git commit -m "Add session-based authentication for patient dashboard

- Add users table to database schema
- Implement login/logout endpoints
- Add user authentication utilities with bcrypt password hashing
- Protect dashboard route with session authentication
- Add avatar dropdown menu with logout functionality
- Update requirements.txt with itsdangerous dependency"
```

### Step 3: Push to Repository

```bash
git push origin main
```

### Step 4: Deploy to Production

**For Aptible:**

```bash
# Set environment variables (if not already set)
aptible config:set \
  SESSION_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") \
  SESSION_SECURE=true \
  ENVIRONMENT=production \
  --app your-app-name

# Deploy
aptible deploy --app your-app-name

# Or if using git-based deployment
git push aptible main
```

**For other platforms:**
- Set environment variables in your platform's dashboard
- Deploy using your standard deployment process
- Ensure the users table migration is run

### Step 5: Run Database Migration

**Via Aptible tunnel:**
```bash
aptible db:tunnel your-app-name
# In another terminal, connect and run the SQL from Step 1
```

**Or via migration script:**
```bash
# If you have database access
python3 -c "
from app.database.schema import *
# Run the users table creation SQL
"
```

### Step 6: Create Admin User

```bash
# Via tunnel
aptible db:tunnel your-app-name
# In another terminal
python3 scripts/create_user.py --username admin --password your-secure-password
```

### Step 7: Verify Deployment

1. Visit your production URL
2. Should redirect to `/login`
3. Login with admin credentials
4. Should see dashboard with avatar in top-right
5. Click avatar → logout should work

## Security Checklist

- [ ] `SESSION_SECRET_KEY` is set and is at least 32 characters
- [ ] `SESSION_SECURE=true` is set (for HTTPS)
- [ ] Database connection uses SSL in production
- [ ] Admin user password is strong
- [ ] `.env` file is in `.gitignore` (already done)
- [ ] No hardcoded secrets in code
- [ ] HTTPS is enabled in production

## Troubleshooting

### Issue: "Invalid username or password" after deployment

**Solution:**
- Verify user exists in database: `SELECT * FROM users;`
- Check password hash is correct
- Try creating user again: `python3 scripts/create_user.py --username admin --password test`

### Issue: Session not persisting

**Solution:**
- Check `SESSION_SECRET_KEY` is set correctly
- Verify `SESSION_SECURE` matches your HTTPS setup
- Check browser console for cookie errors

### Issue: Redirect loop

**Solution:**
- Check `require_auth` dependency is working
- Verify session cookie is being set
- Check for errors in application logs

### Issue: Database connection errors

**Solution:**
- Verify `DATABASE_URL` or individual DB env vars are set
- Check database is accessible from production environment
- Verify SSL mode is correct for remote databases

## Rollback Plan

If issues occur:

1. **Revert code:**
   ```bash
   git revert HEAD
   git push origin main
   aptible deploy --app your-app-name
   ```

2. **Disable authentication temporarily:**
   - Set `SESSION_AUTH_ENABLED = False` in `app/api/routes.py`
   - Redeploy

3. **Remove users table (if needed):**
   ```sql
   DROP TABLE IF EXISTS users CASCADE;
   ```

## Post-Deployment

1. Test login/logout flow
2. Verify patient list is accessible only after login
3. Test avatar dropdown functionality
4. Monitor application logs for errors
5. Create additional users as needed

## Support

For issues or questions:
- Check application logs: `aptible logs --app your-app-name`
- Review error messages in browser console
- Verify environment variables: `aptible config --app your-app-name`

