const axios = require('axios');
const { getAccessToken } = require('./zoomAuth');

const ZOOM_API_BASE = 'https://api.zoom.us/v2';

async function getZoomApiClient() {
  const token = await getAccessToken();
  return axios.create({
    baseURL: ZOOM_API_BASE,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
}

async function getUserMeetings(userId) {
  const client = await getZoomApiClient();
  const response = await client.get(`/users/${userId}/meetings`, {
    params: { type: 'live', page_size: 5 },
  });
  return response.data.meetings || [];
}

async function getMeetingDetails(meetingId) {
  const client = await getZoomApiClient();
  const response = await client.get(`/meetings/${meetingId}`);
  return response.data;
}

async function getRecordingTranscript(meetingId) {
  const client = await getZoomApiClient();
  const response = await client.get(`/meetings/${meetingId}/recordings`);
  const recordings = response.data;

  const transcriptFile = recordings.recording_files?.find(
    (f) => f.file_type === 'TRANSCRIPT' || f.recording_type === 'audio_transcript'
  );

  if (!transcriptFile) {
    return null;
  }

  const token = await getAccessToken();
  const transcriptResponse = await axios.get(transcriptFile.download_url, {
    headers: { Authorization: `Bearer ${token}` },
    params: { access_token: token },
  });

  return transcriptResponse.data;
}

async function getMeetingSummary(meetingId) {
  const client = await getZoomApiClient();
  try {
    const response = await client.get(`/meetings/${meetingId}/meeting_summary`);
    return response.data;
  } catch (err) {
    console.log(`Meeting summary not available for ${meetingId}: ${err.response?.status || err.message}`, err.response?.data || '');
    return null;
  }
}

async function sendChatMessage(botJid, toJid, accountId, content) {
  const client = await getZoomApiClient();
  const response = await client.post('/im/chat/messages', {
    robot_jid: botJid,
    to_jid: toJid,
    account_id: accountId,
    content: content,
  });
  return response.data;
}

module.exports = {
  getUserMeetings,
  getMeetingDetails,
  getRecordingTranscript,
  getMeetingSummary,
  sendChatMessage,
};
