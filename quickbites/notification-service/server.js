const express = require('express');
const app = express();
app.use(express.json());
const PORT = 3005;
const SERVICE = 'notification-service';
const notifications = [];

app.get('/health', (req, res) => res.json({ service: SERVICE, status: 'UP' }));
app.get('/api/notifications', (req, res) => res.json({ service: SERVICE, total: notifications.length, notifications }));
app.post('/api/notifications/send', (req, res) => {
  const { userId, message, channel } = req.body;
  if (!userId || !message) return res.status(400).json({ service: SERVICE, message: 'userId and message required' });
  const n = { id: notifications.length+1, userId, message, channel: channel||'SMS', sentAt: new Date(), status:'Sent' };
  notifications.push(n);
  res.status(201).json({ service: SERVICE, message: 'Notification sent!', notification: n });
});
app.post('/api/notifications/order-update', (req, res) => {
  const { userId, orderId, status } = req.body;
  const msgs = { 'Preparing':`Order #${orderId} is being prepared!`, 'On the way':`Order #${orderId} is on the way!`, 'Delivered':`Order #${orderId} delivered!` };
  const msg = msgs[status] || `Order #${orderId} status: ${status}`;
  const n = { id: notifications.length+1, userId, orderId, message: msg, channel:'SMS', sentAt: new Date(), status:'Sent' };
  notifications.push(n);
  res.status(201).json({ service: SERVICE, message: 'Notification sent!', notification: n });
});
app.listen(PORT, () => console.log(`✅ ${SERVICE} running on port ${PORT}`));

