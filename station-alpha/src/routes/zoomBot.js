const express = require('express');
const router = express.Router();
const { verifyWebhook } = require('../services/zoomAuth');

/**
 * Zoom Chat bot / slash commands are optional for v1 (webhooks-only ingest).
 * This handler stays so Marketplace URL validation and future chat features do not 404.
 */
router.post('/', async (req, res) => {
  try {
    const validation = verifyWebhook(req, process.env.ZOOM_BOT_SECRET_TOKEN);
    if (validation.isValidation) {
      return res.json(validation.response);
    }

    const event = req.body.event;
    const payload = req.body.payload;

    console.log(`Bot event received: ${event}`);

    if (event === 'bot_notification') {
      return res.json({
        head: { text: 'Station Alpha', style: { bold: true } },
        body: [
          {
            type: 'message',
            text:
              'Meetings are captured automatically when they start (Zoom webhooks). Open the **Meeting Intelligence** dashboard to view transcripts and action items — no slash command required.',
          },
        ],
      });
    }

    res.status(200).json({ message: 'Event received' });
  } catch (err) {
    console.error('Bot webhook error:', err.message);
    res.status(200).json({ message: 'Event received' });
  }
});

module.exports = router;
