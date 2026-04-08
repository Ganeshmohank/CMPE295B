/**
 * Writes Zoom + Recall pipeline state into Meeting Intelligence MongoDB collections
 * (same shape as FastAPI / seed data).
 */
const mongoose = require('mongoose');

function getMiDb() {
  if (mongoose.connection.readyState !== 1) {
    throw new Error('MongoDB not connected');
  }
  const name = process.env.DATABASE_NAME || 'meeting_intelligence';
  return mongoose.connection.client.db(name);
}

function now() {
  return new Date();
}

/**
 * @param {string} zoomMeetingId
 * @param {{ topic?: string, host_id?: string, start_time?: string }} objectPayload
 * @returns {Promise<{ insertedId: import('mongodb').ObjectId }>}
 */
async function upsertMeetingStarted(zoomMeetingId, objectPayload) {
  const db = getMiDb();
  const meetings = db.collection('meetings');
  const logs = db.collection('processing_logs');
  const topic = objectPayload.topic || 'Untitled Meeting';
  const startTime = objectPayload.start_time ? new Date(objectPayload.start_time) : now();
  const t = now();

  const existing = await meetings.findOne({ zoom_meeting_id: zoomMeetingId });
  if (!existing) {
    const doc = {
      title: topic,
      source: 'zoom',
      start_time: startTime,
      duration_minutes: 0,
      status: 'pending',
      processing_status: 'in_progress',
      participants_count: 0,
      zoom_meeting_id: zoomMeetingId,
      recall_bot_id: null,
      created_at: t,
      updated_at: t,
    };
    const r = await meetings.insertOne(doc);
    await logs.insertOne({
      meeting_id: r.insertedId,
      stage: 'ingestion',
      status: 'success',
      message: `Zoom meeting.started — ${topic} (Zoom ID ${zoomMeetingId})`,
      processing_time_ms: null,
      timestamp: t,
    });
    return { meetingId: r.insertedId, created: true };
  }

  await meetings.updateOne(
    { _id: existing._id },
    {
      $set: {
        title: topic,
        start_time: startTime,
        status: 'pending',
        processing_status: 'in_progress',
        updated_at: t,
      },
    },
  );
  await logs.insertOne({
    meeting_id: existing._id,
    stage: 'ingestion',
    status: 'success',
    message: `Zoom meeting.started (update) — ${topic}`,
    processing_time_ms: null,
    timestamp: t,
  });
  return { meetingId: existing._id, created: false };
}

/**
 * @param {import('mongodb').ObjectId} meetingId
 * @param {string} recallBotId
 */
async function setRecallBotId(meetingId, recallBotId) {
  const db = getMiDb();
  await db.collection('meetings').updateOne(
    { _id: meetingId },
    { $set: { recall_bot_id: recallBotId, updated_at: now() } },
  );
}

/**
 * @param {string} zoomMeetingId
 * @param {{ topic?: string, host_id?: string, end_time?: string, duration?: number }} objectPayload
 */
async function onMeetingEnded(zoomMeetingId, objectPayload) {
  const db = getMiDb();
  const meetings = db.collection('meetings');
  const logs = db.collection('processing_logs');
  const topic = objectPayload.topic || 'Untitled Meeting';
  const endTime = objectPayload.end_time ? new Date(objectPayload.end_time) : now();
  const durationMin =
    objectPayload.duration != null && !Number.isNaN(Number(objectPayload.duration))
      ? Math.max(0, Math.round(Number(objectPayload.duration)))
      : 0;
  const t = now();

  let meeting = await meetings.findOne({ zoom_meeting_id: zoomMeetingId });
  if (!meeting) {
    const ins = await meetings.insertOne({
      title: topic,
      source: 'zoom',
      start_time: t,
      duration_minutes: durationMin,
      status: 'pending',
      processing_status: 'in_progress',
      participants_count: 0,
      zoom_meeting_id: zoomMeetingId,
      recall_bot_id: null,
      created_at: t,
      updated_at: t,
    });
    meeting = await meetings.findOne({ _id: ins.insertedId });
  } else {
    await meetings.updateOne(
      { _id: meeting._id },
      {
        $set: {
          duration_minutes: durationMin,
          updated_at: t,
        },
      },
    );
    meeting = await meetings.findOne({ _id: meeting._id });
  }

  await logs.insertOne({
    meeting_id: meeting._id,
    stage: 'transcript_processing',
    status: 'pending',
    message: `Meeting ended at ${endTime.toISOString()}; waiting for Recall.ai transcript`,
    processing_time_ms: null,
    timestamp: t,
  });

  return { meeting, recallBotId: meeting.recall_bot_id || null };
}

/**
 * @param {import('mongodb').ObjectId} meetingMongoId
 * @param {string} transcriptText
 * @param {Array<{ speaker?: string, text: string }>} segments
 * @param {Array<{ text: string, assignee?: string, dueDate?: string }>} extractedItems
 * @param {string} topic
 * @param {string | null} [extractionWarning] e.g. OpenAI 429 — transcript still saved
 */
async function finalizeSuccess(
  meetingMongoId,
  transcriptText,
  segments,
  extractedItems,
  topic,
  extractionWarning = null,
) {
  const db = getMiDb();
  const meetings = db.collection('meetings');
  const transcripts = db.collection('transcripts');
  const actionItems = db.collection('action_items');
  const logs = db.collection('processing_logs');
  const t = now();
  const t0 = Date.now();

  await transcripts.deleteMany({ meeting_id: meetingMongoId });
  const rawText = transcriptText || '';
  await transcripts.insertOne({
    meeting_id: meetingMongoId,
    raw_text: rawText,
    segments: segments && segments.length ? segments : [{ speaker: null, text: rawText }],
    transcript_length: rawText.length,
    created_at: t,
  });

  await actionItems.deleteMany({ meeting_id: meetingMongoId });

  for (const item of extractedItems) {
    const rawText = item.text || item.description || item.task || '';
    const desc = String(rawText).trim() || 'Action item';
    const assignee = item.assignee || item.owner || item.owner_name || '';
    let due = null;
    if (item.dueDate && String(item.dueDate).trim()) {
      const d = String(item.dueDate).trim().slice(0, 32);
      due = d.length >= 10 ? d.slice(0, 10) : d;
    }
    await actionItems.insertOne({
      meeting_id: meetingMongoId,
      description: desc,
      owner_name: assignee && String(assignee).trim() ? String(assignee).trim() : null,
      due_date: due,
      priority: 'medium',
      confidence: 0.82,
      status: 'pending_review',
      source_snippet: desc.slice(0, 280),
      created_at: t,
      updated_at: t,
    });
  }

  const elapsed = Date.now() - t0;
  await meetings.updateOne(
    { _id: meetingMongoId },
    {
      $set: {
        status: 'completed',
        processing_status: 'processed',
        updated_at: t,
      },
    },
  );

  const baseMsg = `Extracted ${extractedItems.length} action item(s) from "${topic}"`;
  const message = extractionWarning ? `${baseMsg}. ${extractionWarning}` : baseMsg;
  const logStatus =
    extractionWarning && extractedItems.length === 0 ? 'skipped' : 'success';

  await logs.insertOne({
    meeting_id: meetingMongoId,
    stage: 'extraction',
    status: logStatus,
    message,
    processing_time_ms: elapsed,
    timestamp: t,
  });
}

/**
 * @param {import('mongodb').ObjectId} meetingMongoId
 * @param {string} reason
 */
async function finalizeNoTranscript(meetingMongoId, reason) {
  const db = getMiDb();
  const t = now();
  await db.collection('meetings').updateOne(
    { _id: meetingMongoId },
    {
      $set: {
        status: 'completed',
        processing_status: 'processed',
        updated_at: t,
      },
    },
  );
  await db.collection('processing_logs').insertOne({
    meeting_id: meetingMongoId,
    stage: 'transcript_processing',
    status: 'skipped',
    message: reason,
    processing_time_ms: null,
    timestamp: t,
  });
}

/**
 * @param {import('mongodb').ObjectId} meetingMongoId
 * @param {string} errMessage
 */
async function finalizeError(meetingMongoId, errMessage) {
  const db = getMiDb();
  const t = now();
  await db.collection('meetings').updateOne(
    { _id: meetingMongoId },
    {
      $set: {
        status: 'completed',
        processing_status: 'failed',
        updated_at: t,
      },
    },
  );
  await db.collection('processing_logs').insertOne({
    meeting_id: meetingMongoId,
    stage: 'transcript_processing',
    status: 'failed',
    message: errMessage.slice(0, 500),
    processing_time_ms: null,
    timestamp: t,
  });
}

/**
 * @param {string} zoomMeetingId
 */
async function getRecallBotIdForZoomMeeting(zoomMeetingId) {
  const db = getMiDb();
  const m = await db.collection('meetings').findOne({ zoom_meeting_id: zoomMeetingId });
  if (!m || !m.recall_bot_id) return null;
  return String(m.recall_bot_id);
}

module.exports = {
  upsertMeetingStarted,
  setRecallBotId,
  onMeetingEnded,
  finalizeSuccess,
  finalizeNoTranscript,
  finalizeError,
  getRecallBotIdForZoomMeeting,
};
