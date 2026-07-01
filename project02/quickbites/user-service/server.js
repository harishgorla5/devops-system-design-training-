const express = require('express');
const app = express();
app.use(express.json());

const PORT = 3001;
const SERVICE = 'user-service';

const users = [
  { id: 1, name: 'Harish',   email: 'harish@quickbite.com',   phone: '9876543210', address: 'Hyderabad' },
  { id: 2, name: 'Lokesh', email: 'lokesh@quickbite.com',  phone: '9876543211', address: 'Bangalore' },
  { id: 3, name: 'Nethaji',  email: 'nethaji@quickbite.com',  phone: '9876543212', address: 'Mumbai'    },
  { id: 4, name: 'Vishnu',  email: 'vishnu@quickbite.com',  phone: '9876543213', address: 'Chennai'   },
];

app.get('/health', (req, res) => {
  res.json({ service: SERVICE, status: 'UP', timestamp: new Date() });
});

app.get('/api/users', (req, res) => {
  console.log(`[${SERVICE}] GET /api/users`);
  res.json({ service: SERVICE, total: users.length, users });
});

app.get('/api/users/:id', (req, res) => {
  const user = users.find(u => u.id === parseInt(req.params.id));
  if (!user) return res.status(404).json({ service: SERVICE, message: 'User not found' });
  res.json({ service: SERVICE, user });
});

app.post('/api/users/register', (req, res) => {
  const { name, email, phone, address } = req.body;
  if (!name || !email) return res.status(400).json({ service: SERVICE, message: 'name and email required' });
  const newUser = { id: users.length + 1, name, email, phone, address };
  users.push(newUser);
  res.status(201).json({ service: SERVICE, message: 'User registered successfully', user: newUser });
});

app.listen(PORT, () => console.log(`✅ ${SERVICE} running on port ${PORT}`));

