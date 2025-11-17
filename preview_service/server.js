const express = require('express');
const cors = require('cors');
require('dotenv').config();

const app = express();
const PORT = 8086;

// Middleware
app.use(cors());
app.use(express.json());

// Basic health check
app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'PrizeMe Node.js backend is running' });
});

// Start server
app.listen(PORT, () => {
  console.log(`🎯 PrizeMe Node.js backend running on port ${PORT}`);
  console.log(`📊 Using existing .env configuration`);
});