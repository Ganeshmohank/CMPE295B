const express = require('express');
const router = express.Router();
const { verifyWebhook } = require('../services/zoomAuth');
const { extractActionItems } = require('../services/openaiService');
const { sendBotToMeeting, getBotTranscript, waitForBotDone } = require('../services/recallService');
const { getMeetingDetails } = require('../services/zoomApi');
const mi = require('../services/meetingIntelligenceSync');

/** Zoom numeric meeting id -> Recall bot id (memory; also persisted on meeting doc). */
const activeBots = {};

function transcriptToTextAndSegments(transcript) {
  if (!transcript) return { text: '', segments: [] };
  if (Array.isArray(transcript)) {
    const segments = transcript.map((t) => {
      const words = t.words?.map((w) => w.text).join(' ') || t.text || '';
      return { speaker: t.speaker || null, text: words };
    });
    const text = segments.map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text)).join('\n');
    return { text, segments };
  }
  if (typeof transcript === 'string') {
    return { text: transcript, segments: [{ speaker: null, text: transcript }] };
  }
  const raw = JSON.stringify(transcript);
  return { text: raw, segments: [{ speaker: null, text: raw }] };
}

router.post('/', async (req, res) => {
  try {
    console.log(`Incoming webhook event: ${req.body.event}`, JSON.stringify(req.body).substring(0, 200));

    const s2sValidation = verifyWebhook(req, process.env.ZOOM_S2S_SECRET_TOKEN);
    if (s2sValidation.isValidation) {
      if (!s2sValidation.response) {
        return res.status(500).json({ error: s2sValidation.validationError || 'validation_misconfigured' });
      }
      console.log('Validation challenge received (S2S Secret Token), building response...');
      res.on('finish', () => {
        console.log(`[zoom] URL validation done — HTTP ${res.statusCode} (this request is finished; no further logs until the next webhook)`);
      });
      return res.status(200).json(s2sValidation.response);
    }

    const validation = verifyWebhook(req, process.env.ZOOM_BOT_SECRET_TOKEN);
    if (validation.isValidation) {
      if (!validation.response) {
        return res.status(500).json({ error: validation.validationError || 'validation_misconfigured' });
      }
      console.log('Validation challenge received (bot Secret Token), building response...');
      res.on('finish', () => {
        console.log(`[zoom] URL validation done — HTTP ${res.statusCode}`);
      });
      return res.status(200).json(validation.response);
    }

    const event = req.body.event;
    const payload = req.body.payload;

    console.log(`Received Zoom event: ${event}`);

    if (event === 'meeting.started') {
      const meetingId = String(payload.object.id);
      const topic = payload.object.topic || 'Untitled Meeting';

      const { meetingId: mongoId } = await mi.upsertMeetingStarted(meetingId, payload.object);

      try {
        let passcode = payload.object.password || payload.object.pstn_password || '';
        if (!passcode) {
          try {
            const details = await getMeetingDetails(meetingId);
            passcode = details.password || details.encrypted_password || '';
            console.log(`Fetched passcode from Zoom API for meeting ${meetingId}: ${passcode ? 'found' : 'none'}`);
          } catch (e) {
            console.log(`Could not fetch meeting details for passcode: ${e.message}`);
          }
        }
        const meetingUrl = passcode
          ? `https://zoom.us/j/${meetingId}?pwd=${passcode}`
          : `https://zoom.us/j/${meetingId}`;
        const botName = process.env.RECALL_BOT_DISPLAY_NAME || 'ZTA Notetaker';
        console.log(`Sending Recall bot to: ${meetingUrl}`);
        const bot = await sendBotToMeeting(meetingUrl, botName);
        activeBots[meetingId] = bot.id;
        await mi.setRecallBotId(mongoId, bot.id);
        console.log(`Recall bot ${bot.id} sent to meeting ${meetingId}`);
      } catch (botErr) {
        console.error(`Failed to send Recall bot to meeting ${meetingId}:`, botErr.response?.data || botErr.message);
      }
    }

    if (event === 'meeting.ended') {
      const meetingId = String(payload.object.id);
      const topic = payload.object.topic || 'Untitled Meeting';

      const { meeting, recallBotId: persistedBot } = await mi.onMeetingEnded(meetingId, payload.object);
      const mongoMeetingId = meeting._id;

      const botId = activeBots[meetingId] || persistedBot;
      console.log(`Meeting ${meetingId} ended. Recall bot: ${botId || 'none'}`);

      if (botId) {
        setImmediate(async () => {
          /** If Recall returned text, always try to persist it even if OpenAI or finalizeSuccess fails. */
          let transcriptTextForSalvage = null;
          let segmentsForSalvage = null;

          try {
            console.log(`Waiting for Recall bot ${botId} to finish processing...`);
            await waitForBotDone(botId);

            const transcript = await getBotTranscript(botId);
            if (transcript) {
              const { text: transcriptText, segments } = transcriptToTextAndSegments(transcript);
              transcriptTextForSalvage = transcriptText;
              segmentsForSalvage = segments;
              console.log(`Got transcript (${transcriptText.length} chars) for meeting ${meetingId}`);

              let actionItems = [];
              let extractionWarning = null;
              try {
                actionItems = await extractActionItems(transcriptText, topic);
                console.log(`Extracted ${actionItems.length} action items for meeting ${meetingId}`);
              } catch (aiErr) {
                const msg = aiErr.message || String(aiErr);
                console.error(`OpenAI action extraction failed for meeting ${meetingId}:`, msg);
                extractionWarning = `OpenAI skipped (${msg.slice(0, 200)}) — add billing/quota or fix API key; transcript kept.`;
              }

              await mi.finalizeSuccess(
                mongoMeetingId,
                transcriptText,
                segments,
                actionItems,
                topic,
                extractionWarning,
              );
            } else {
              await mi.finalizeNoTranscript(
                mongoMeetingId,
                'No transcript returned from Recall.ai for this meeting.',
              );
            }
            delete activeBots[meetingId];
          } catch (err) {
            const msg = err.message || String(err);
            console.error(`Error processing Recall transcript for meeting ${meetingId}:`, msg);

            if (transcriptTextForSalvage != null && String(transcriptTextForSalvage).length > 0) {
              try {
                await mi.finalizeSuccess(
                  mongoMeetingId,
                  transcriptTextForSalvage,
                  segmentsForSalvage && segmentsForSalvage.length
                    ? segmentsForSalvage
                    : [{ speaker: null, text: transcriptTextForSalvage }],
                  [],
                  topic,
                  `Pipeline error after transcript was fetched (${msg.slice(0, 180)}). Transcript saved without action items.`,
                );
                console.log(`Salvaged transcript for meeting ${meetingId} after error`);
              } catch (salvageErr) {
                console.error(`Salvage failed for meeting ${meetingId}:`, salvageErr.message);
                await mi.finalizeError(mongoMeetingId, msg);
              }
            } else {
              await mi.finalizeError(mongoMeetingId, msg || 'Unknown error');
            }
            delete activeBots[meetingId];
          }
        });
      } else {
        await mi.finalizeNoTranscript(
          mongoMeetingId,
          'No Recall bot was associated with this meeting; skipped transcript and extraction.',
        );
        console.log(`No Recall bot for meeting ${meetingId}, skipping transcript`);
      }
    }

    res.status(200).json({ message: 'Event received' });
  } catch (err) {
    console.error('Webhook error:', err.message);
    res.status(200).json({ message: 'Event received' });
  }
});

module.exports = router;
