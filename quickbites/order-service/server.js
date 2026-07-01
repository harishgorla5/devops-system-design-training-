const express = require('express');
const app = express();
app.use(express.json());
const PORT = 3002;
const SERVICE = 'order-service';

const orders = [
  { id:1, userId:1, restaurant:'Biryani Palace', items:['Chicken Biryani','Raita'], total:320, status:'Delivered' },
  { id:2, userId:2, restaurant:'Pizza Corner',   items:['Margherita Pizza','Coke'], total:450, status:'On the way' },
  { id:3, userId:3, restaurant:'Burger Hub',     items:['Veg Burger','Fries'],      total:220, status:'Preparing' },
  { id:4, userId:1, restaurant:'Dosa World',     items:['Masala Dosa','Coffee'],    total:180, status:'Delivered' },
];

app.get('/health', (req, res) => res.json({ service: SERVICE, status: 'UP' }));
app.get('/api/orders', (req, res) => res.json({ service: SERVICE, total: orders.length, orders }));
app.get('/api/orders/user/:userId', (req, res) => {
  const userOrders = orders.filter(o => o.userId === parseInt(req.params.userId));
  res.json({ service: SERVICE, total: userOrders.length, orders: userOrders });
});
app.post('/api/orders', (req, res) => {
  const { userId, restaurant, items, total } = req.body;
  if (!userId || !restaurant || !items) return res.status(400).json({ service: SERVICE, message: 'Missing fields' });
  const newOrder = { id: orders.length+1, userId, restaurant, items, total: total||0, status:'Preparing' };
  orders.push(newOrder);
  res.status(201).json({ service: SERVICE, message: 'Order placed!', order: newOrder });
});
app.listen(PORT, () => console.log(`✅ ${SERVICE} running on port ${PORT}`));

