const OpenAI = require('openai');

function getOpenAI() {
  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    throw new Error('OPENAI_API_KEY is not set');
  }
  return new OpenAI({ apiKey: key });
}

async function extractActionItems(transcript, meetingTopic) {
  const openai = getOpenAI();
  const response = await openai.chat.completions.create({
    model: 'gpt-4o',
    messages: [
      {
        role: 'system',
        content: `You are an expert meeting analyst. Given a meeting transcript, extract all action items discussed.
For each action item, identify:
- The task description (text)
- Who it's assigned to (assignee, or empty string)
- Any deadline or due date (dueDate as string, or empty string)

You MUST respond with valid JSON only, using this exact shape:
{"actionItems":[{"text":"","assignee":"","dueDate":""}]}
Use an empty array for actionItems if there are none.`,
      },
      {
        role: 'user',
        content: `Meeting Topic: ${meetingTopic}\n\nTranscript:\n${transcript}`,
      },
    ],
    temperature: 0.3,
    response_format: { type: 'json_object' },
  });

  try {
    const content = response.choices[0].message.content;
    const parsed = JSON.parse(content);
    const items =
      parsed.actionItems || parsed.items || parsed.action_items || (Array.isArray(parsed) ? parsed : []);
    return Array.isArray(items) ? items : [];
  } catch (err) {
    console.error('Failed to parse OpenAI response:', err);
    return [];
  }
}

module.exports = { extractActionItems };
