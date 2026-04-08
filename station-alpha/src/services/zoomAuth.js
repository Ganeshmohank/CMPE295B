const axios = require('axios');

let s2sToken = null;
let s2sTokenExpiry = 0;

async function getAccessToken() {
  if (s2sToken && Date.now() < s2sTokenExpiry) {
    return s2sToken;
  }

  const credentials = Buffer.from(
    `${process.env.ZOOM_S2S_CLIENT_ID}:${process.env.ZOOM_S2S_CLIENT_SECRET}`
  ).toString('base64');

  const response = await axios.post(
    'https://zoom.us/oauth/token',
    new URLSearchParams({
      grant_type: 'account_credentials',
      account_id: process.env.ZOOM_S2S_ACCOUNT_ID,
    }),
    {
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }
  );

  s2sToken = response.data.access_token;
  s2sTokenExpiry = Date.now() + (response.data.expires_in - 60) * 1000;
  console.log('S2S token obtained successfully');
  return s2sToken;
}

function verifyWebhook(req, secretToken) {
  const body = req.body || {};
  const event = body.event;
  if (event !== 'endpoint.url_validation') {
    return { isValidation: false };
  }
  const plainToken =
    (body.payload && body.payload.plainToken) ||
    body.plainToken ||
    (body.payload && body.payload.plain_token);
  if (!plainToken || !secretToken) {
    console.error(
      'Zoom URL validation: missing plainToken or ZOOM_S2S_SECRET_TOKEN / ZOOM_BOT_SECRET_TOKEN in .env',
    );
    return {
      isValidation: true,
      response: null,
      validationError: 'missing_token_or_secret',
    };
  }
  const crypto = require('crypto');
  const hashForValidation = crypto
    .createHmac('sha256', secretToken)
    .update(plainToken)
    .digest('hex');
  return {
    isValidation: true,
    response: { plainToken, encryptedToken: hashForValidation },
  };
}

module.exports = { getAccessToken, verifyWebhook };
