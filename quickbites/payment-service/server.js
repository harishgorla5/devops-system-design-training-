const express = require('express');
const app = express();
app.use(express.json());
const PORT = 3004;
const SERVICE = 'payment-service';
const payments = [
  { id:1, orderId:1, userId:1, amount:320, method:'UPI',         status:'Success', txnId:'TXN001' },
  { id:2, orderId:2, userId:2, amount:450, method:'Credit Card', status:'Success', txnId:'TXN002' },
  { id:3, orderId:3, userId:3, amount:220, method:'Cash',        status:'Pending', txnId:'TXN003' },
];
app.get('/health', (req, res) => res.json({ service: SERVICE, status: 'UP' }));
app.get('/api/payments', (req, res) => res.json({ service: SERVICE, total: payments.length, payments }));
app.post('/api/payments', (req, res) => {
  const { orderId, userId, amount, method } = req.body;
  if (!orderId || !amount || !method) return res.status(400).json({ service: SERVICE, message: 'Missing fields' });
  const success = Math.random() > 0.1;
  const payment = { id: payments.length+1, orderId, userId, amount, method,
    status: success?'Success':'Failed', txnId:'TXN'+String(payments.length+1).padStart(3,'0') };
  payments.push(payment);
  res.status(success?201:402).json({ service: SERVICE, message: success?'Payment successful!':'Payment failed!', payment });
});
app.listen(PORT, () => console.log(`✅ ${SERVICE} running on port ${PORT}`));

