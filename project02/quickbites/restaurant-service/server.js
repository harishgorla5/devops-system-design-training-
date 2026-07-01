const express = require('express');
const app = express();
app.use(express.json());
const PORT = 3003;
const SERVICE = 'restaurant-service';

const restaurants = [
  { id:1, name:'Biryani Palace', city:'Hyderabad', rating:4.5, cuisine:'Indian',
    menu:[{item:'Chicken Biryani',price:280},{item:'Mutton Biryani',price:350},{item:'Veg Biryani',price:200}] },
  { id:2, name:'Pizza Corner', city:'Bangalore', rating:4.2, cuisine:'Italian',
    menu:[{item:'Margherita Pizza',price:350},{item:'Pepperoni Pizza',price:420},{item:'Garlic Bread',price:80}] },
  { id:3, name:'Burger Hub', city:'Mumbai', rating:4.0, cuisine:'Fast Food',
    menu:[{item:'Veg Burger',price:120},{item:'Chicken Burger',price:160},{item:'Fries',price:80}] },
  { id:4, name:'Dosa World', city:'Chennai', rating:4.7, cuisine:'South Indian',
    menu:[{item:'Masala Dosa',price:120},{item:'Plain Dosa',price:80},{item:'Filter Coffee',price:40}] },
];

app.get('/health', (req, res) => res.json({ service: SERVICE, status: 'UP' }));
app.get('/api/restaurants', (req, res) => {
  const list = restaurants.map(r => ({ id:r.id, name:r.name, city:r.city, rating:r.rating, cuisine:r.cuisine }));
  res.json({ service: SERVICE, total: list.length, restaurants: list });
});
app.get('/api/restaurants/:id', (req, res) => {
  const r = restaurants.find(r => r.id === parseInt(req.params.id));
  if (!r) return res.status(404).json({ service: SERVICE, message: 'Not found' });
  res.json({ service: SERVICE, restaurant: r });
});
app.listen(PORT, () => console.log(`✅ ${SERVICE} running on port ${PORT}`));

