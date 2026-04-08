require('dotenv').config();
const express = require('express');
const cors = require('cors');
const mongoose = require('mongoose');
const zoomWebhookRoutes = require('./routes/zoomWebhooks');
const zoomBotRoutes = require('./routes/zoomBot');
const oauthCallbackRoutes = require('./routes/oauthCallback');

const app = express();
const PORT = process.env.PORT || 3001;


app.use(cors());
app.use(express.json());

mongoose.connect(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 10000,
  socketTimeoutMS: 45000,
})
  .then(() => console.log('Connected to MongoDB'))
  .catch(err => {
    console.error('MongoDB connection error:', err.message);
    console.log('Server will continue running - MongoDB will retry on next request');
  });

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

/* Zoom "Event notification endpoint URL" often pasted without path — accept POST / too. */
app.use('/zoom/events', zoomWebhookRoutes);
app.use('/', zoomWebhookRoutes);
app.use('/zoom/botmessage', zoomBotRoutes);
app.use('/zoom/oauth/callback', oauthCallbackRoutes);
/* Meeting list/detail lives on Meeting Intelligence FastAPI (port 8000), not here. */

app.listen(PORT, () => {
  console.log(`Station Alpha (Zoom ingest) listening on http://127.0.0.1:${PORT}`);
  console.log('  Webhooks: POST /zoom/events  OR POST / (root) if Zoom URL has no path');
});
