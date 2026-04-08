const axios = require('axios');

const RECALL_BASE_URL = `https://${process.env.RECALL_REGION || 'us-west-2'}.recall.ai/api/v1`;

function getHeaders() {
  return {
    Authorization: `Token ${process.env.RECALL_API_KEY}`,
    'Content-Type': 'application/json',
  };
}

async function sendBotToMeeting(meetingUrl, botName = 'ZTA Notetaker') {
  const response = await axios.post(
    `${RECALL_BASE_URL}/bot`,
    {
      meeting_url: meetingUrl,
      bot_name: botName,
      recording_config: {
        transcript: {
          provider: {
            meeting_captions: {},
          },
        },
      },
    },
    { headers: getHeaders() }
  );
  console.log(`Recall bot sent to meeting: ${response.data.id}`);
  return response.data;
}

async function getBotStatus(botId) {
  const response = await axios.get(`${RECALL_BASE_URL}/bot/${botId}`, {
    headers: getHeaders(),
  });
  return response.data;
}

async function getBotTranscript(botId) {
  const bot = await getBotStatus(botId);

  if (!bot.recordings || bot.recordings.length === 0) {
    return null;
  }

  const recording = bot.recordings[0];
  const transcriptShortcut = recording.media_shortcuts?.transcript;

  if (!transcriptShortcut?.data?.download_url) {
    return null;
  }

  const transcriptResponse = await axios.get(transcriptShortcut.data.download_url);
  return transcriptResponse.data;
}

async function waitForBotDone(botId, maxWaitMs = 120000) {
  const startTime = Date.now();
  const pollInterval = 5000;

  while (Date.now() - startTime < maxWaitMs) {
    const bot = await getBotStatus(botId);
    const latestStatus = bot.status_changes?.[bot.status_changes.length - 1]?.code;

    if (latestStatus === 'done') {
      return bot;
    }
    if (latestStatus === 'fatal' || latestStatus === 'error') {
      throw new Error(`Recall bot failed with status: ${latestStatus}`);
    }

    await new Promise((resolve) => setTimeout(resolve, pollInterval));
  }

  throw new Error('Recall bot timed out waiting for done status');
}

module.exports = { sendBotToMeeting, getBotStatus, getBotTranscript, waitForBotDone };
