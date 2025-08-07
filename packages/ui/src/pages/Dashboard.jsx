import React, { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

function Dashboard() {
  const [saves, setSaves] = useState([]);
  const [selectedSave, setSelectedSave] = useState('');
  const [countries, setCountries] = useState([]);
  const [selectedCountry, setSelectedCountry] = useState('');
  const [metrics, setMetrics] = useState([]);

  // Fetch all saves on mount
  useEffect(() => {
    fetch('/api/saves')
      .then(res => res.json())
      .then(data => setSaves(data))
      .catch(err => console.error('Error fetching saves:', err));
  }, []);

  // Fetch countries when a save is selected
  useEffect(() => {
    if (!selectedSave) return;
    fetch(`/api/countries?save_id=${selectedSave}`)
      .then(res => res.json())
      .then(data => setCountries(data))
      .catch(err => console.error('Error fetching countries:', err));
  }, [selectedSave]);

  // Fetch metrics when a country is selected
  useEffect(() => {
    if (!selectedCountry) return;
    fetch(`/api/country_metrics?country_tag=${selectedCountry}`)
      .then(res => res.json())
      .then(data => setMetrics(data))
      .catch(err => console.error('Error fetching metrics:', err));
  }, [selectedCountry]);

  // Group metrics by name
  const metricGroups = metrics.reduce((groups, m) => {
    const { name, amount, recorded_at } = m;
    if (!groups[name]) groups[name] = [];
    groups[name].push({ recorded_at, amount });
    return groups;
  }, {});

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Dashboard</h2>

      {/* Save selector */}
      <div className="mb-4">
        <label className="block mb-1">Select Save:</label>
        <select
          className="border rounded px-2 py-1"
          value={selectedSave}
          onChange={e => {
            setSelectedSave(e.target.value);
            setSelectedCountry('');
            setMetrics([]);
          }}
        >
          <option value="">-- Choose --</option>
          {saves.map(save => (
            <option key={save.save_id} value={save.save_id}>
              {save.filename} ({new Date(save.saved_at).toLocaleDateString()})
            </option>
          ))}
        </select>
      </div>

      {/* Country selector */}
      {countries.length > 0 && (
        <div className="mb-6">
          <label className="block mb-1">Select Country:</label>
          <select
            className="border rounded px-2 py-1"
            value={selectedCountry}
            onChange={e => setSelectedCountry(e.target.value)}
          >
            <option value="">-- Choose --</option>
            {countries.map(c => (
              <option key={c.country_tag} value={c.country_tag}>
                {c.name} ({c.country_tag})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Charts */}
      {selectedCountry && (
        <div className="space-y-8">
          {Object.entries(metricGroups).map(([metricName, data]) => (
            <div key={metricName} className="bg-white p-4 rounded shadow">
              <h3 className="text-lg font-medium mb-2">{metricName}</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={
                  // Sort by date ascending
                  data.sort(
                    (a, b) => new Date(a.recorded_at) - new Date(b.recorded_at)
                  )
                }>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="recorded_at" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="amount" name={metricName} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Dashboard;