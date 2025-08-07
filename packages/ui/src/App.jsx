import React, { useState, useEffect } from 'react';

export default function Settings() {
  const [savesPath, setSavesPath] = useState('');
  const [gameDbPath, setGameDbPath] = useState('');
  const [status, setStatus] = useState(null);

  // Fetch current settings
  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        setSavesPath(data.vic3_saves_path || '');
        setGameDbPath(data.game_data_db_path || '');
      })
      .catch(err => console.error('Error fetching settings:', err));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus('saving');
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vic3_saves_path: savesPath,
          game_data_db_path: gameDbPath
        }),
      });
      if (res.ok) {
        setStatus('saved');
      } else {
        setStatus('error');
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  };

  return (
    <div className="max-w-xl mx-auto py-8">
      <h2 className="text-2xl font-semibold mb-4">Settings</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block mb-1 font-medium">Victoria 3 Saves Path</label>
          <input
            type="text"
            value={savesPath}
            onChange={e => setSavesPath(e.target.value)}
            className="w-full border rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="block mb-1 font-medium">Game Data DB Path</label>
          <input
            type="text"
            value={gameDbPath}
            onChange={e => setGameDbPath(e.target.value)}
            className="w-full border rounded px-3 py-2"
          />
        </div>
        <button
          type="submit"
          className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
        >
          Save Settings
        </button>
      </form>
      {status === 'saving' && <p className="mt-4 text-blue-600">Saving...</p>}
      {status === 'saved' && <p className="mt-4 text-green-600">Settings saved!</p>}
      {status === 'error' && <p className="mt-4 text-red-600">Error saving settings.</p>}
    </div>
  );
}

