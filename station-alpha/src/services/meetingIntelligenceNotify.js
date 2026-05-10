/**
 * Optional callbacks from station-alpha → Meeting Intelligence FastAPI after Mongo writes.
 */
const axios = require('axios');

/**
 * Ask the API to publish a Notion recap page (narrative + action items) for this meeting.
 * No-op if MEETING_INTELLIGENCE_API_URL is unset.
 *
 * @param {import('mongodb').ObjectId} meetingMongoId
 */
async function triggerNotionRecap(meetingMongoId) {
  const base = (process.env.MEETING_INTELLIGENCE_API_URL || '').trim();
  if (!base) {
    return;
  }
  const secret = (process.env.MEETING_INTELLIGENCE_INTERNAL_SECRET || '').trim();
  const url = `${base.replace(/\/$/, '')}/meetings/${String(meetingMongoId)}/notion-recap`;
  const headers = { 'Content-Type': 'application/json' };
  if (secret) {
    headers['X-Internal-Secret'] = secret;
  }
  try {
    const res = await axios.post(url, { force: false }, { headers, timeout: 120000 });
    const d = res.data || {};
    if (d.posted) {
      console.log(`[mi] Notion recap posted: ${d.notion_url || d.page_id || 'ok'}`);
    } else {
      console.log(`[mi] Notion recap skipped: ${d.skipped_reason || 'unknown'}`);
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || String(e);
    console.warn(`[mi] Notion recap request failed: ${msg}`);
  }
}

module.exports = { triggerNotionRecap };
