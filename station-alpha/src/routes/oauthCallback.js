const express = require('express');
const router = express.Router();
const axios = require('axios');
router.get('/', async (req, res) => {
  const { code } = req.query;

  if (!code) {
    return res.status(400).send('Missing authorization code');
  }

  const publicBase = (process.env.PUBLIC_URL || '').replace(/\/$/, '');
  if (!publicBase) {
    return res.status(500).send('PUBLIC_URL is not set in .env (use your tunnel or API base URL, no trailing slash)');
  }

  try {
    const credentials = Buffer.from(
      `${process.env.ZOOM_BOT_CLIENT_ID}:${process.env.ZOOM_BOT_CLIENT_SECRET}`
    ).toString('base64');

    const response = await axios.post(
      'https://zoom.us/oauth/token',
      new URLSearchParams({
        grant_type: 'authorization_code',
        code: code,
        redirect_uri: `${publicBase}/zoom/oauth/callback`,
      }),
      {
        headers: {
          Authorization: `Basic ${credentials}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      }
    );

    console.log('OAuth tokens received:', {
      access_token: response.data.access_token ? '***' : 'missing',
      refresh_token: response.data.refresh_token ? '***' : 'missing',
      scope: response.data.scope,
    });

    res.send(`
      <html>
        <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f9fafb;">
          <div style="text-align: center; padding: 40px; background: white; border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <h1 style="color: #4f46e5;">ZTA Bot Authorized!</h1>
            <p style="color: #6b7280;">The bot is now connected to your Zoom account.</p>
            <p style="color: #6b7280;">You can now use <code>/zta</code> in Zoom Chat.</p>
          </div>
        </body>
      </html>
    `);
  } catch (err) {
    console.error('OAuth error:', err.response?.data || err.message);
    res.status(500).send(`OAuth error: ${err.response?.data?.reason || err.message}`);
  }
});

module.exports = router;
