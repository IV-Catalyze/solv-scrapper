# API Authentication Guide

This guide explains how to use the authentication system for the Patient Data API.

## Overview

The API uses **JWT (JSON Web Tokens)** for authentication, following industry-standard practices. This provides:
- Secure, time-limited access tokens
- Automatic token expiration
- Support for multiple clients
- Production-ready security

## Quick Start

### 1. Generate an Access Token

```bash
curl -X POST "http://localhost:8000/auth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your-client-name",
    "expires_hours": 24
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_at": "2024-11-07T14:22:03.000Z",
  "expires_in": 86400,
  "client_id": "your-client-name"
}
```

### 2. Use the Token in API Requests

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  "http://localhost:8000/patients?locationId=AXjwbE"
```

## Authentication Methods

### Method 1: JWT Bearer Token (Recommended)

**Best for:** Production integrations, automated systems, multiple clients

**How it works:**
1. Client requests a token from `/auth/token` with a `client_id`
2. Server generates a JWT token with expiration
3. Client includes token in `Authorization: Bearer <token>` header
4. Server validates token on each request

**Advantages:**
- Time-limited access (automatic expiration)
- No shared secrets to manage
- Can track which client made requests
- Industry standard (OAuth 2.0 compatible)

### Method 2: API Key (Alternative)

**Best for:** Simple integrations, testing, single-client scenarios

**How it works:**
1. Server administrator sets `API_KEY` environment variable
2. Client includes key in `X-API-Key` header
3. Server validates key on each request

**Advantages:**
- Simple to use
- No token generation needed
- Good for testing

**Disadvantages:**
- No automatic expiration
- Shared secret must be rotated manually
- Less flexible for multiple clients

## Configuration

### Environment Variables

Set these in your `.env` file or environment:

```env
# Required for production (minimum 32 characters)
JWT_SECRET_KEY=your-very-secure-secret-key-minimum-32-characters-long

# Optional: Static API key for simple authentication
API_KEY=your-static-api-key-here

# Optional: Token expiration in minutes (default: 1440 = 24 hours)
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Generating a Secure Secret Key

**Python:**
```python
import secrets
print(secrets.token_urlsafe(32))
```

**OpenSSL:**
```bash
openssl rand -base64 32
```

**Online:** Use a secure password generator (minimum 32 characters)

## Production Best Practices

### 1. Secure Secret Management

- **Never commit secrets to version control**
- Use environment variables or secret management systems (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate `JWT_SECRET_KEY` periodically (invalidates all existing tokens)
- Use different secrets for different environments (dev, staging, production)

### 2. Token Management

- **Store tokens securely**: Use environment variables or secure vaults
- **Implement token refresh**: Automatically renew tokens before expiration
- **Monitor token usage**: Log client_id for audit trails
- **Set appropriate expiration**: Balance security (shorter) vs convenience (longer)

### 3. Client Implementation

**Python example:**
```python
import requests
from datetime import datetime, timedelta

class APIClient:
    def __init__(self, base_url, client_id):
        self.base_url = base_url
        self.client_id = client_id
        self.token = None
        self.token_expires = None
    
    def get_token(self):
        """Get or refresh access token"""
        if self.token and self.token_expires and datetime.utcnow() < self.token_expires:
            return self.token
        
        response = requests.post(
            f"{self.base_url}/auth/token",
            json={"client_id": self.client_id, "expires_hours": 24}
        )
        data = response.json()
        self.token = data["access_token"]
        self.token_expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        return self.token
    
    def get_patients(self, location_id):
        """Make authenticated API request"""
        token = self.get_token()
        response = requests.get(
            f"{self.base_url}/patients",
            params={"locationId": location_id},
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()

# Usage
client = APIClient("http://localhost:8000", "my-client")
patients = client.get_patients("AXjwbE")
```

**JavaScript/Node.js example:**
```javascript
const axios = require('axios');

class APIClient {
  constructor(baseUrl, clientId) {
    this.baseUrl = baseUrl;
    this.clientId = clientId;
    this.token = null;
    this.tokenExpires = null;
  }

  async getToken() {
    if (this.token && this.tokenExpires && new Date() < this.tokenExpires) {
      return this.token;
    }

    const response = await axios.post(`${this.baseUrl}/auth/token`, {
      client_id: this.clientId,
      expires_hours: 24
    });

    this.token = response.data.access_token;
    this.tokenExpires = new Date(response.data.expires_at);
    return this.token;
  }

  async getPatients(locationId) {
    const token = await this.getToken();
    const response = await axios.get(`${this.baseUrl}/patients`, {
      params: { locationId },
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  }
}

// Usage
const client = new APIClient('http://localhost:8000', 'my-client');
client.getPatients('AXjwbE').then(patients => console.log(patients));
```

## Error Handling

### 401 Unauthorized

**Causes:**
- Missing `Authorization` header
- Invalid or expired token
- Invalid API key

**Resolution:**
- Generate a new token using `/auth/token`
- Verify your `Authorization` header format: `Bearer <token>`
- Check token expiration time

**Example error:**
```json
{
  "detail": "Could not validate credentials"
}
```

## Security Considerations

1. **HTTPS Only**: Always use HTTPS in production. Never send tokens over unencrypted connections.

2. **Token Storage**: 
   - Don't store tokens in browser localStorage (XSS risk)
   - Use httpOnly cookies or secure memory storage
   - Clear tokens on logout

3. **Token Rotation**: 
   - Implement automatic token refresh
   - Rotate `JWT_SECRET_KEY` periodically
   - Revoke compromised tokens immediately

4. **Rate Limiting**: 
   - Implement rate limiting on `/auth/token` endpoint
   - Monitor for suspicious token generation patterns

5. **Audit Logging**: 
   - Log all authentication attempts
   - Track token usage by client_id
   - Monitor for unusual patterns

## Troubleshooting

### Token generation fails

- Check that `JWT_SECRET_KEY` is set in environment
- Verify the request format matches the API specification
- Check server logs for detailed error messages

### Token validation fails

- Verify token hasn't expired (check `expires_at`)
- Ensure `JWT_SECRET_KEY` matches the one used to generate the token
- Check token format (should start with `eyJ`)

### API key not working

- Verify `API_KEY` is set in server environment
- Check header name is exactly `X-API-Key` (case-sensitive)
- Ensure no extra spaces in the API key value

## How Other Teams Use It

This authentication pattern follows industry standards used by:

- **GitHub API**: Uses Bearer tokens
- **Stripe API**: Uses API keys and Bearer tokens
- **AWS APIs**: Uses access keys and session tokens
- **Google Cloud**: Uses OAuth 2.0 tokens
- **Microsoft Azure**: Uses access tokens

The implementation here is similar to OAuth 2.0 Client Credentials flow, which is widely adopted for server-to-server authentication.

## Additional Resources

- [JWT.io](https://jwt.io/) - JWT debugger and information
- [OAuth 2.0 RFC](https://oauth.net/2/) - OAuth 2.0 specification
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/) - FastAPI security documentation

